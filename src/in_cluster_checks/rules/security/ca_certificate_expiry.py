"""
CA certificate expiry validation rules.

This module contains orchestrator rules for checking critical Certificate Authority (CA)
certificates. CA expiry is catastrophic - if a CA expires, all certificates signed by it
become invalid, causing cluster-wide authentication failures.
"""

import base64
import json
from datetime import datetime, timezone

from cryptography import x509

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives


class KubeletCaExpiryCheck(OrchestratorRule):
    """
    Check if the kubelet CA certificate is expiring soon.

    The kubelet CA certificate is stored in the kube-apiserver-to-kubelet-signer secret
    in the openshift-kube-apiserver-operator namespace. This certificate is critical
    for kubelet authentication - if it expires, all kubelet certificates become invalid.

    Background:
    - Kubelet CA is valid for 365 days
    - Should auto-rotate at ~80% lifecycle (~292 days, leaving ~73 days remaining)
    - If certificate reaches 30 days remaining, CA rotation has been failing for ~11 months

    Alert threshold: 30 days remaining (CA rotation should have happened at ~73 days)
    Severity: CRITICAL - entire cluster node authentication breaks if CA expires
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "kubelet_ca_expiry_check"
    title = "Check kubelet CA certificate expiry"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Security-%E2%80%90-Check-kubelet-CA-certificate-expiry",
    ]

    # Alert threshold: 30 days (CA rotation should have happened at ~73 days, ~292 days after creation)
    CRITICAL_DAYS = 30

    # Secret containing the kubelet CA certificate
    SECRET_NAME = "kube-apiserver-to-kubelet-signer"
    SECRET_NAMESPACE = "openshift-kube-apiserver-operator"

    def run_rule(self):
        """Check kubelet CA certificate expiry."""
        try:
            ca_info = self._get_kubelet_ca_info()
        except UnExpectedSystemOutput:
            return RuleResult.failed(
                f"Failed to retrieve kubelet CA certificate from secret " f"{self.SECRET_NAMESPACE}/{self.SECRET_NAME}"
            )

        if ca_info.get("status") == "error":
            return RuleResult.failed(f"Failed to parse kubelet CA certificate: {ca_info['message']}")

        days_remaining = ca_info["days_remaining"]
        end_date = ca_info["end_date"]

        return self._evaluate_ca_status(days_remaining, end_date)

    def _evaluate_ca_status(self, days_remaining, end_date):
        """
        Evaluate CA status and return appropriate result.

        Args:
            days_remaining: Days until CA expires
            end_date: Certificate expiration date string

        Returns:
            RuleResult with appropriate status
        """
        if days_remaining <= 0:
            return RuleResult.failed(
                f"CRITICAL: Kubelet CA certificate EXPIRED {abs(days_remaining)} days ago!\n"
                f"Secret: {self.SECRET_NAMESPACE}/{self.SECRET_NAME}\n"
                f"Expiry Date: {end_date}\n\n"
                f"All kubelet node certificates are invalid. Cluster authentication is broken."
            )

        if days_remaining <= self.CRITICAL_DAYS:
            failure_duration = 365 - 73 - days_remaining
            return RuleResult.failed(
                f"CRITICAL: Kubelet CA certificate expires in {days_remaining} days "
                f"(threshold: {self.CRITICAL_DAYS} days)\n"
                f"Secret: {self.SECRET_NAMESPACE}/{self.SECRET_NAME}\n"
                f"Expiry Date: {end_date}\n\n"
                f"CA rotation should have happened at ~73 days remaining (~292 days after creation).\n"
                f"This means CA auto-rotation has been failing for ~{failure_duration} days.\n"
                f"If CA expires, ALL kubelet certificates become invalid, breaking cluster authentication."
            )

        return RuleResult.passed(
            f"Kubelet CA certificate is valid for {days_remaining} more days\n"
            f"Secret: {self.SECRET_NAMESPACE}/{self.SECRET_NAME}\n"
            f"Expiry Date: {end_date}"
        )

    def _get_kubelet_ca_info(self):
        """
        Retrieve and parse kubelet CA certificate from secret.

        Returns:
            dict: Certificate info with keys: end_date, days_remaining, status, message

        Raises:
            UnExpectedSystemOutput: If secret retrieval fails
        """
        secret_data = self._fetch_secret()
        cert_b64 = secret_data.get("data", {}).get("tls.crt", "")

        if not cert_b64:
            return {
                "status": "error",
                "message": f"No tls.crt data found in secret {self.SECRET_NAMESPACE}/{self.SECRET_NAME}",
            }

        return self._parse_certificate(cert_b64)

    def _fetch_secret(self):
        """
        Fetch the kubelet CA secret from the cluster.

        Returns:
            dict: Secret data

        Raises:
            UnExpectedSystemOutput: If secret retrieval or parsing fails
        """
        try:
            _, out, _ = self.run_oc_command(
                "get",
                ["secret", self.SECRET_NAME, "-n", self.SECRET_NAMESPACE, "-o", "json"],
                timeout=45,
            )
        except UnExpectedSystemOutput as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"oc get secret {self.SECRET_NAME} -n {self.SECRET_NAMESPACE} -o json",
                output=str(e),
                message=f"Failed to retrieve secret: {e}",
            )

        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"oc get secret {self.SECRET_NAME} -n {self.SECRET_NAMESPACE} -o json",
                output=out,
                message=f"Failed to parse secret JSON: {e}",
            )

    def _parse_certificate(self, cert_b64):
        """
        Parse base64-encoded certificate and extract expiry info.

        Args:
            cert_b64: Base64-encoded certificate

        Returns:
            dict: Certificate info with end_date, days_remaining, status
        """
        try:
            cert_pem = base64.b64decode(cert_b64)
            cert = x509.load_pem_x509_certificate(cert_pem)
            end_date = cert.not_valid_after_utc
            days_remaining = (end_date - datetime.now(timezone.utc)).days

            return {
                "end_date": end_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "days_remaining": days_remaining,
                "status": "ok",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to parse certificate: {e}",
            }
