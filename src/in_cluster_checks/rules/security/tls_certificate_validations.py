"""
TLS certificate validation rules.

This module checks OpenShift infrastructure TLS certificates stored in secrets.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

from cryptography import x509

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.infra_namespaces import COMMON_INFRA_NAMESPACES


class TlsCertificateExpiry(OrchestratorRule):
    """
    Check if infrastructure TLS certificates don't expire in 14 days.

    Retrieves TLS-type secrets from infrastructure namespaces and validates that their
    certificates are not expired or expiring soon.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_tls_certs_are_valid"
    title = "Check if infrastructure TLS certificates don't expire in 14 days"
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482936",
    ]

    WARNING_DAYS = 14
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

        for item in items:
            name = item["metadata"]["name"]
            namespace = item["metadata"]["namespace"]
            cert_info = self._check_secret_cert(name, namespace, item)

            if cert_info.get("status") == "error":
                errors.append(cert_info)
            elif cert_info["remaining"] <= timedelta(0):
                expired.append(cert_info)
            elif cert_info["remaining"] <= timedelta(days=self.WARNING_DAYS):
                expiring_soon.append(cert_info)
            else:
                valid.append(cert_info)

        return expired, expiring_soon, valid, errors

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

            return {
                "name": name,
                "namespace": namespace,
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "days_remaining": remaining.days,
                "remaining": remaining,
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
