"""
Certificate expiry validation rules.

Ported from support/HealthChecks/flows/Security/Certificate/allcertificate_expiry_dates.py
Adapted for OpenShift in-cluster checks on node filesystems.
"""

from datetime import datetime

from in_cluster_checks.core.rule import PrerequisiteResult, Rule, RuleResult
from in_cluster_checks.utils.enums import Objectives


class NodeCertificateExpiry(Rule):
    """
    Check certificate expiry dates on OpenShift nodes.

    Validates that certificates in common paths are not expiring soon.
    Warns if certificates will expire within 30 days.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "node_certificate_expiry"
    title = "Verify node certificates are not expiring soon"

    # Days before expiry to start warning
    WARNING_DAYS = 30

    # Common certificate paths on OpenShift nodes
    CERT_PATHS = [
        "/var/lib/kubelet/pki/kubelet-client-current.pem",
        "/var/lib/kubelet/pki/kubelet-server-current.pem",
        "/etc/kubernetes/static-pod-certs/secrets/etcd-all-certs/etcd-serving-*.crt",
        "/etc/kubernetes/static-pod-certs/secrets/etcd-all-certs/etcd-peer-*.crt",
    ]

    def is_prerequisite_fulfilled(self):
        """Check if openssl is available."""
        rc, _, _ = self.run_cmd("which openssl")
        if rc != 0:
            return PrerequisiteResult.not_met("openssl is not available on this system")
        return PrerequisiteResult.met()

    def _get_cert_end_date(self, cert_path):
        """
        Get certificate end date using openssl.

        Args:
            cert_path: Path to certificate file

        Returns:
            tuple: (success: bool, end_date_str: str, error_msg: str)
        """
        cmd = f"openssl x509 -enddate -noout -in {cert_path}"
        rc, out, err = self.run_cmd(cmd)

        if rc != 0:
            return False, None, f"Failed to read certificate: {err}"

        # Output format: "notAfter=Dec 31 23:59:59 2025 GMT"
        if "=" not in out:
            return False, None, f"Unexpected openssl output format: {out}"

        end_date_str = out.split("=")[1].strip()
        return True, end_date_str, None

    def _parse_date(self, date_str):
        """
        Parse certificate date string.

        Args:
            date_str: Date string from openssl (e.g., "Dec 31 23:59:59 2025 GMT")

        Returns:
            datetime object or None if parsing fails
        """
        # Remove GMT/UTC timezone suffix for parsing
        date_str = date_str.replace(" GMT", "").replace(" UTC", "")

        try:
            return datetime.strptime(date_str, "%b %d %H:%M:%S %Y")
        except ValueError:
            return None

    def _calculate_days_remaining(self, end_date):
        """
        Calculate days remaining until certificate expires.

        Args:
            end_date: datetime object of expiry date

        Returns:
            int: Days remaining (negative if expired)
        """
        now = datetime.now()
        delta = end_date - now
        return delta.days

    def _check_certificate(self, cert_path):
        """
        Check a single certificate for expiry.

        Args:
            cert_path: Path to certificate file

        Returns:
            dict: Certificate status info
        """
        # Check if file exists
        if not self.file_utils.is_file_exist(cert_path):
            return {
                "path": cert_path,
                "status": "not_found",
                "message": "Certificate file not found",
            }

        # Get end date
        success, end_date_str, error_msg = self._get_cert_end_date(cert_path)
        if not success:
            return {
                "path": cert_path,
                "status": "error",
                "message": error_msg,
            }

        # Parse date
        end_date = self._parse_date(end_date_str)
        if end_date is None:
            return {
                "path": cert_path,
                "status": "error",
                "message": f"Failed to parse date: {end_date_str}",
            }

        # Calculate days remaining
        days_remaining = self._calculate_days_remaining(end_date)

        # Determine status
        if days_remaining <= 0:
            status = "expired"
            message = f"Certificate expired {abs(days_remaining)} days ago"
        elif days_remaining <= self.WARNING_DAYS:
            status = "expiring_soon"
            message = f"Certificate will expire in {days_remaining} days"
        else:
            status = "ok"
            message = f"Certificate valid for {days_remaining} more days"

        return {
            "path": cert_path,
            "status": status,
            "end_date": end_date_str,
            "days_remaining": days_remaining,
            "message": message,
        }

    def _expand_glob_paths(self, cert_paths):
        """
        Expand glob patterns in certificate paths.

        Args:
            cert_paths: List of paths (may contain glob patterns)

        Returns:
            List of actual file paths
        """
        expanded_paths = []
        for path in cert_paths:
            if "*" in path:
                # Use ls to expand glob
                rc, out, _ = self.run_cmd(f"ls {path} 2>/dev/null")
                if rc == 0 and out.strip():
                    expanded_paths.extend(out.strip().split("\n"))
            else:
                expanded_paths.append(path)
        return expanded_paths

    def run_rule(self):
        """Check all certificates on this node."""
        # Expand glob patterns
        cert_paths = self._expand_glob_paths(self.CERT_PATHS)

        # Check each certificate
        cert_results = []
        for cert_path in cert_paths:
            result = self._check_certificate(cert_path)
            cert_results.append(result)

        # Categorize results
        expired = [r for r in cert_results if r["status"] == "expired"]
        expiring_soon = [r for r in cert_results if r["status"] == "expiring_soon"]
        errors = [r for r in cert_results if r["status"] == "error"]
        ok = [r for r in cert_results if r["status"] == "ok"]

        # Build system_info table
        table_data = []
        for r in cert_results:
            table_data.append(
                [
                    r["path"],
                    r.get("end_date", "N/A"),
                    r.get("days_remaining", "N/A"),
                    r["status"],
                    r["message"],
                ]
            )

        system_info = {
            "headers": ["Certificate Path", "End Date", "Days Remaining", "Status", "Message"],
            "rows": table_data,
        }

        # Determine result
        if expired:
            expired_paths = [r["path"] for r in expired]
            message = f"Found {len(expired)} expired certificate(s) on node:\n" + "\n".join(
                f"  - {p}" for p in expired_paths
            )
            return RuleResult.failed(message, system_info=system_info)

        if expiring_soon:
            expiring_paths = [f"{r['path']} ({r['days_remaining']} days)" for r in expiring_soon]
            message = (
                f"Found {len(expiring_soon)} certificate(s) expiring within "
                f"{self.WARNING_DAYS} days:\n" + "\n".join(f"  - {p}" for p in expiring_paths)
            )
            return RuleResult.warning(message, system_info=system_info)

        if errors and not ok:
            # All checks failed - this is a problem
            error_paths = [r["path"] for r in errors]
            message = f"Failed to check {len(errors)} certificate(s):\n" + "\n".join(f"  - {p}" for p in error_paths)
            return RuleResult.failed(message, system_info=system_info)

        # All checks passed or certificates not found (which is OK for optional certs)
        checked_count = len([r for r in cert_results if r["status"] in ["ok", "expiring_soon"]])
        return RuleResult.passed(f"All {checked_count} found certificate(s) are valid", system_info=system_info)
