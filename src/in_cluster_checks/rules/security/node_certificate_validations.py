"""
Node certificate validation rules.

This module contains rules for checking node-level certificates and their rotation mechanisms.
Node certificates rotate every 30 days automatically, and these rules ensure both the certificates
themselves and the rotation mechanism are healthy.
"""

import json
from datetime import datetime

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, Rule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class NodeCertificateExpiry(Rule):
    """
    Check etcd certificate expiry dates on OpenShift nodes.

    Monitors etcd serving and peer certificates which have 3-year validity
    and only rotate during cluster upgrades. Warns if certificates will
    expire within 30 days.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "node_certificate_expiry"
    title = "Verify node certificates are not expiring soon"
    links = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Security-%E2%80%90-Node-certificate-expiry",
    ]

    # Days before expiry to start warning
    WARNING_DAYS = 30

    # etcd certificate paths on OpenShift nodes
    # etcd certificates have 3-year validity and are not rotated automatically
    CERT_PATHS = [
        SafeCmdString("/etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-*.crt"),
        SafeCmdString("/etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-peer-*.crt"),
    ]

    def is_prerequisite_fulfilled(self):
        """Check if openssl is available."""
        rc, _, _ = self.run_cmd(SafeCmdString("which openssl"))
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
        cmd = SafeCmdString("openssl x509 -enddate -noout -in {cert_path}").format(cert_path=cert_path)
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
            if "*" in str(path):
                # Use ls to expand glob
                rc, out, _ = self.run_cmd(SafeCmdString("ls {path} 2>/dev/null").format(path=path))
                if rc == 0 and out.strip():
                    expanded_paths.extend(out.strip().split("\n"))
            else:
                expanded_paths.append(str(path))
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


class KubeletCsrHealthCheck(OrchestratorRule):
    """
    Check kubelet Certificate Signing Request (CSR) health.

    Kubelet node certificates rotate every 30 days automatically. This rule
    detects when certificate rotation fails by monitoring CSR status.

    Alert condition: CSRs stuck in Pending or Denied state
    Severity: WARNING - fixable by manually approving CSRs
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "kubelet_csr_health_check"
    title = "Check kubelet CSR health"
    links = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Security-‐-Check-kubelet-CSR-health",
    ]

    def run_rule(self):
        """Check kubelet CSR health by querying cluster CSRs."""
        try:
            csr_data = self._get_csr_data()
        except UnExpectedSystemOutput:
            return RuleResult.failed("Failed to retrieve Certificate Signing Requests from cluster")

        pending_csrs, denied_csrs = self._filter_kubelet_csrs(csr_data)

        return self._evaluate_csr_status(pending_csrs, denied_csrs)

    def _evaluate_csr_status(self, pending_csrs, denied_csrs):
        """
        Evaluate CSR status and return appropriate result.

        Args:
            pending_csrs: List of pending CSR names
            denied_csrs: List of denied CSR names

        Returns:
            RuleResult with appropriate status
        """
        if not pending_csrs and not denied_csrs:
            return RuleResult.passed("All kubelet CSRs are approved and healthy")

        error_messages = []

        if denied_csrs:
            error_messages.append(
                f"CRITICAL: {len(denied_csrs)} kubelet CSR(s) have been DENIED:\n  "
                + "\n  ".join(denied_csrs)
                + "\n\nDenied CSRs indicate certificate rotation was explicitly rejected.\n"
                "Kubelet certificates will NOT rotate automatically."
            )

        if pending_csrs:
            error_messages.append(
                f"WARNING: {len(pending_csrs)} kubelet CSR(s) are PENDING approval:\n  "
                + "\n  ".join(pending_csrs)
                + "\n\nPending CSRs indicate the 30-day automatic rotation mechanism is not working.\n"
                "Certificates will expire if CSRs remain pending."
            )

        return RuleResult.warning("\n\n".join(error_messages))

    def _get_csr_data(self):
        """
        Retrieve all Certificate Signing Requests from the cluster.

        Returns:
            dict: Parsed CSR data from JSON output

        Raises:
            UnExpectedSystemOutput: If CSR retrieval or parsing fails
        """
        _, out, _ = self.oc_api.run_oc_command(
            "get",
            ["csr", "-o", "json"],
            timeout=45,
        )

        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="oc get csr -o json",
                output=out,
                message=f"Failed to parse CSR JSON: {e}",
            )

    def _filter_kubelet_csrs(self, csr_data):
        """
        Filter CSRs to find kubelet-related ones in Pending or Denied state.

        Args:
            csr_data: Parsed CSR JSON data

        Returns:
            tuple: (pending_csrs, denied_csrs) - lists of CSR names
        """
        pending_csrs = []
        denied_csrs = []

        for item in csr_data.get("items", []):
            metadata = item.get("metadata", {})
            csr_name = metadata.get("name", "unknown")

            # Filter for kubelet CSRs (username contains "system:node:")
            spec = item.get("spec", {})
            username = spec.get("username", "")

            if not username.startswith("system:node:"):
                continue

            # Check CSR status
            status = item.get("status", {})
            conditions = status.get("conditions", [])

            if not conditions:
                # No conditions means Pending
                pending_csrs.append(csr_name)
                continue

            # Check if CSR is Approved or Denied
            csr_status_found = False
            for condition in conditions:
                condition_type = condition.get("type", "")
                if condition_type == "Denied":
                    denied_csrs.append(csr_name)
                    csr_status_found = True
                    break
                elif condition_type == "Approved":
                    csr_status_found = True
                    break

            # If no Approved or Denied condition found, treat as Pending
            if not csr_status_found:
                pending_csrs.append(csr_name)

        return pending_csrs, denied_csrs
