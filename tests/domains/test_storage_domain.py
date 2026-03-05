"""Tests for Storage validation domain."""

from in_cluster_checks.domains.storage_domain import StorageValidationDomain
from in_cluster_checks.rules.storage.storage_validations import (
    CephOsdTreeWorks,
    CephSlowOps,
    CheckPoolSize,
    IsCephHealthOk,
    IsCephOSDsNearFull,
    IsOSDsUp,
    IsOSDsWeightOK,
    OrphanCsiVolumes,
    OsdJournalError,
)


def test_storage_domain_name():
    """Test domain name."""
    domain = StorageValidationDomain()
    assert domain.domain_name() == "storage"


def test_storage_domain_rules():
    """Test domain returns correct rules."""
    domain = StorageValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 9
    assert CephOsdTreeWorks in rules
    assert CephSlowOps in rules
    assert CheckPoolSize in rules
    assert IsCephHealthOk in rules
    assert IsCephOSDsNearFull in rules
    assert IsOSDsUp in rules
    assert IsOSDsWeightOK in rules
    assert OrphanCsiVolumes in rules
    assert OsdJournalError in rules
