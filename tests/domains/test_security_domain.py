"""Tests for Security validation domain."""

from in_cluster_checks.domains.security_domain import SecurityValidationDomain
from in_cluster_checks.rules.security.certificate_expiry import NodeCertificateExpiry
from in_cluster_checks.rules.security.tls_certificate_expiry import TlsCertificateExpiry


def test_security_domain_name():
    """Test domain name."""
    domain = SecurityValidationDomain()
    assert domain.domain_name() == "security"


def test_security_domain_rules():
    """Test domain returns correct rules."""
    domain = SecurityValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 2
    assert NodeCertificateExpiry in rules
    assert TlsCertificateExpiry in rules
