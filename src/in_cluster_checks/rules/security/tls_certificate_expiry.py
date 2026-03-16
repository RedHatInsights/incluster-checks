import base64
import json
from datetime import datetime, timezone

from cryptography import x509

from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives


class TlsCertificateExpiry(OrchestratorRule):
    """
    Check if all TLS certificates in Kubernetes secrets don't expire in 14 days.

    Retrieves all TLS-type secrets from the cluster and validates that their
    certificates are not expired or expiring soon.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_tls_certs_are_valid"
    title = "Check if all TLS certificates don't expire in 14 days"

    WARNING_DAYS = 14

    def run_rule(self):
        secrets_data = self._get_tls_secrets()
        items = secrets_data.get("items", [])

        if not items:
            return RuleResult.passed("No TLS secrets found in the cluster")

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
            elif cert_info["days_remaining"] <= 0:
                expired.append(cert_info)
            elif cert_info["days_remaining"] <= self.WARNING_DAYS:
                expiring_soon.append(cert_info)
            else:
                valid.append(cert_info)

        return expired, expiring_soon, valid, errors

    def _check_secret_cert(self, name, namespace, item):
        cert_b64 = item.get("data", {}).get("tls.crt", "")

        if not cert_b64:
            return {"name": name, "namespace": namespace, "status": "error", "message": "No tls.crt data in secret"}

        try:
            cert_pem = base64.b64decode(cert_b64)
            cert = x509.load_pem_x509_certificate(cert_pem)
            end_date = cert.not_valid_after_utc
            days_remaining = (end_date - datetime.now(timezone.utc)).days

            return {
                "name": name,
                "namespace": namespace,
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "days_remaining": days_remaining,
            }
        except Exception as e:
            return {"name": name, "namespace": namespace, "status": "error", "message": str(e)}

    def _build_result(self, expired, expiring_soon, valid, errors, system_info):
        if expired:
            names = [f"{c['namespace']}/{c['name']}" for c in expired]
            return RuleResult.failed(
                f"Found {len(expired)} expired TLS certificate(s): {names}",
                system_info=system_info,
            )

        if expiring_soon:
            names = [f"{c['namespace']}/{c['name']} ({c['days_remaining']} days)" for c in expiring_soon]
            message = f"Found {len(expiring_soon)} TLS certificate(s) expiring within {self.WARNING_DAYS} days:\n"
            message += "\n".join(f"  - {n}" for n in names)
            return RuleResult.warning(message, system_info=system_info)

        if errors and not valid:
            return RuleResult.failed(
                f"Failed to check {len(errors)} TLS certificate(s)",
                system_info=system_info,
            )

        return RuleResult.passed(
            f"All {len(valid)} TLS certificate(s) are valid",
            system_info=system_info,
        )

    def _get_tls_secrets(self):
        _, out, _ = self.run_oc_command(
            "get", ["secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json"]
        )
        return json.loads(out)

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
