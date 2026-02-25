"""Tests for Storage validation domain."""

from openshift_in_cluster_checks.domains.storage_domain import StorageValidationDomain
from openshift_in_cluster_checks.rules.storage.storage_validations import (
    CephOsdTreeWorks,
)


def test_storage_domain_name():
    """Test domain name."""
    domain = StorageValidationDomain()
    assert domain.domain_name() == "storage"


def test_storage_domain_rules():
    """Test domain returns correct rules."""
    domain = StorageValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 1
    assert CephOsdTreeWorks in rules
