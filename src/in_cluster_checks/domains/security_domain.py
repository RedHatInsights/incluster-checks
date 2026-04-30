"""
Security rule domain for OpenShift cluster.

Orchestrates security-related healthcheck validators.
Based on support/HealthChecks/flows/Security/Certificate/allcertificate_expiry_dates.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.security.ca_certificate_validations import KubeletCaExpiryCheck
from in_cluster_checks.rules.security.node_certificate_validations import KubeletCsrHealthCheck, NodeCertificateExpiry
from in_cluster_checks.rules.security.tls_certificate_validations import TlsCertificateExpiry


class SecurityValidationDomain(RuleDomain):
    """
    Security rule domain for OpenShift.

    Validates security-related health on cluster nodes.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "security"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of security validators to run.

        Returns:
            List of Rule classes (ported from HC Security validations)
        """
        return [
            NodeCertificateExpiry,
            TlsCertificateExpiry,
            KubeletCaExpiryCheck,
            KubeletCsrHealthCheck,
        ]
