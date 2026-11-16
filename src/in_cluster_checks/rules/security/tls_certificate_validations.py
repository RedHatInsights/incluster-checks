"""
TLS certificate validation rules.

This module checks OpenShift infrastructure TLS certificates stored in secrets.
"""

import base64
import json
import re
from datetime import UTC, datetime, timedelta

from cryptography import x509

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.infra_namespaces import COMMON_INFRA_NAMESPACES

# A whole Go duration, so partial values such as "360h-invalid" are rejected rather than truncated
GO_DURATION_PATTERN = re.compile(r"(?:\d+(?:\.\d+)?[hms])+")
# Each amount/unit pair within it: "360h0m0s" -> [("360", "h"), ("0", "m"), ("0", "s")]
GO_DURATION_PART_PATTERN = re.compile(r"(\d+(?:\.\d+)?)([hms])")
DURATION_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}


class TlsCertificateExpiry(OrchestratorRule):
    """
    Check if infrastructure TLS certificates don't expire in 14 days.

    Retrieves TLS-type secrets from infrastructure namespaces and validates that their
    certificates are not expired or expiring soon.

    Certificates that OpenShift operators rotate automatically are not reported while
    they are still inside their declared rotation window, since replacement is pending
    rather than overdue.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_tls_certs_are_valid"
    title = "Check if infrastructure TLS certificates don't expire in 14 days"
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482936",
    ]

    WARNING_DAYS = 14
    REFRESH_PERIOD_ANNOTATION = "certificates.openshift.io/refresh-period"
    TRUST_ROTATION_GRACE_DIVISOR = 10
    VALIDITY_ROTATION_FRACTION = 0.8
    INFRA_NAMESPACES = COMMON_INFRA_NAMESPACES + (
        "openshift-config",
        "openshift-config-managed",
    )

    def run_rule(self):
        """Validate TLS certificates in the configured infrastructure namespaces."""
        items = self._get_tls_secrets()

        if not items:
            return RuleResult.passed("No TLS secrets found in infrastructure namespaces")

        expired, expiring_soon, valid, errors = self._check_all_secrets(items)
        system_info = self._build_system_info(expired, expiring_soon, valid, errors)
        return self._build_result(expired, expiring_soon, valid, errors, system_info)

    def _check_all_secrets(self, items):
        expired = []
        expiring_soon = []
        valid = []
        errors = []
        now = datetime.now(UTC)

        for item in items:
            name = item["metadata"]["name"]
            namespace = item["metadata"]["namespace"]
            cert_info = self._check_secret_cert(name, namespace, item)

            if cert_info.get("status") == "error":
                errors.append(cert_info)
                continue

            remaining = cert_info["remaining"]
            if remaining <= timedelta(0):
                expired.append(cert_info)
            elif remaining <= timedelta(days=self.WARNING_DAYS) and not self._is_rotation_pending(cert_info, now):
                expiring_soon.append(cert_info)
            else:
                valid.append(cert_info)

        return expired, expiring_soon, valid, errors

    @staticmethod
    def _parse_go_duration(value):
        """
        Convert a Go duration string to a timedelta, or None when it is absent or unrecognized.

        Operators write the refresh period in Go's duration format, for example "360h0m0s" for
        15 days or "1h30m0s" for 90 minutes. The whole value must match, so a partial value such
        as "360h-invalid" or a negative one is rejected instead of being read as 15 days. Values
        too large for a timedelta are rejected the same way.

        Returning None lets the caller fall back to the plain expiry threshold instead of trusting
        a value it could not read.
        """
        if not value or not GO_DURATION_PATTERN.fullmatch(value):
            return None

        pairs = GO_DURATION_PART_PATTERN.findall(value)
        try:
            return timedelta(seconds=sum(float(amount) * DURATION_UNIT_SECONDS[unit] for amount, unit in pairs))
        except OverflowError:
            return None

    def _is_rotation_pending(self, cert_info, now):
        """
        Report whether an automatically rotated certificate is still inside its rotation window.

        OpenShift operators replace a managed certificate at not_before + refresh_period, then wait
        refresh_period / 10 so a freshly rotated signer reaches every trust bundle before the leaf is
        re-issued. Within that window the certificate is pending replacement rather than at risk, so a
        short-lived certificate can legitimately drop below WARNING_DAYS before being replaced.

        Rotation is also forced once 80% of the actual validity has elapsed, whichever comes first. A
        leaf issued close to its signer's expiry is cut short to the signer's remaining lifetime while
        keeping the configured refresh period, which can leave refresh_period longer than the validity
        itself. Honouring only the refresh period would then suppress the warning until the certificate
        expired, so the earlier of the two deadlines decides.

        Certificates without the annotation are not managed this way and are never treated as pending.
        """
        refresh_period = cert_info.get("refresh_period")
        if not refresh_period:
            return False

        not_before = cert_info["not_before"]
        grace = refresh_period / self.TRUST_ROTATION_GRACE_DIVISOR
        refresh_deadline = not_before + refresh_period + grace
        validity_deadline = not_before + (cert_info["not_after"] - not_before) * self.VALIDITY_ROTATION_FRACTION
        return now <= min(refresh_deadline, validity_deadline)

    def _check_secret_cert(self, name, namespace, item):
        """Decode a secret's certificate and report its expiry or parse error."""
        cert_b64 = item.get("data", {}).get("tls.crt", "")

        if not cert_b64:
            return {"name": name, "namespace": namespace, "status": "error", "message": "No tls.crt data in secret"}

        try:
            cert_pem = base64.b64decode(cert_b64)
            cert = x509.load_pem_x509_certificate(cert_pem)
            end_date = cert.not_valid_after_utc
            remaining = end_date - datetime.now(UTC)
            annotations = item["metadata"].get("annotations") or {}

            return {
                "name": name,
                "namespace": namespace,
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "days_remaining": remaining.days,
                "remaining": remaining,
                "not_before": cert.not_valid_before_utc,
                "not_after": end_date,
                "refresh_period": self._parse_go_duration(annotations.get(self.REFRESH_PERIOD_ANNOTATION)),
            }
        except Exception as e:
            return {"name": name, "namespace": namespace, "status": "error", "message": str(e)}

    def _build_result(self, expired, expiring_soon, valid, errors, system_info):
        if expired:
            names = [f"{c['namespace']}/{c['name']}" for c in expired]
            message = f"Found {len(expired)} expired TLS certificate(s):\n"
            message += "\n".join(f"  - {n}" for n in names)
            return RuleResult.failed(
                message,
                system_info=system_info,
            )

        if expiring_soon:
            names = [f"{c['namespace']}/{c['name']} ({c['days_remaining']} days)" for c in expiring_soon]
            message = f"Found {len(expiring_soon)} TLS certificate(s) expiring within {self.WARNING_DAYS} days:\n"
            message += "\n".join(f"  - {n}" for n in names)
            return RuleResult.warning(message, system_info=system_info)

        if errors:
            msg = f"Failed to check {len(errors)} TLS certificate(s)"
            if not valid:
                return RuleResult.failed(msg, system_info=system_info)
            return RuleResult.warning(msg, system_info=system_info)

        return RuleResult.passed(
            f"All {len(valid)} TLS certificate(s) are valid",
            system_info=system_info,
        )

    def _get_tls_secrets(self):
        """Read TLS secrets per namespace, skipping only absent namespaces."""
        items = []
        for namespace in self.INFRA_NAMESPACES:
            try:
                _, out, _ = self.oc_api.run_oc_command(
                    "get", ["secret", "--field-selector=type=kubernetes.io/tls", "-n", namespace, "-o", "json"]
                )
            except UnExpectedSystemOutput as exc:
                if f'namespaces "{namespace}" not found' not in exc.output:
                    raise
                continue
            items.extend(json.loads(out).get("items", []))
        return items

    def _build_system_info(self, expired, expiring_soon, valid, errors):
        all_certs = expired + expiring_soon + valid
        rows = []
        for c in all_certs:
            status = "expired" if c in expired else "expiring_soon" if c in expiring_soon else "ok"
            rows.append([c["name"], c["namespace"], c.get("end_date", "N/A"), c.get("days_remaining", "N/A"), status])
        for e in errors:
            rows.append([e["name"], e["namespace"], "N/A", "N/A", f"error: {e['message']}"])

        return {
            "headers": ["Secret Name", "Namespace", "End Date", "Days Remaining", "Status"],
            "rows": rows,
        }
