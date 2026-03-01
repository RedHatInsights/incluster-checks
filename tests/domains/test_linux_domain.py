"""Tests for Linux validation domain."""

from in_cluster_checks.domains.linux_domain import LinuxValidationDomain
from in_cluster_checks.rules.linux.linux_validations import (
    AuditdBacklogLimit,
    ClockSynchronized,
    IsHostReachable,
    SelinuxMode,
    SystemdServicesStatus,
    TooManyOpenFilesCheck,
    VerifyDuNotHang,
    YumlockFileCheck,
)


def test_linux_domain_name():
    """Test domain name."""
    domain = LinuxValidationDomain()
    assert domain.domain_name() == "linux"


def test_linux_domain_rules():
    """Test domain returns correct rules."""
    domain = LinuxValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 8
    assert SystemdServicesStatus in rules
    assert IsHostReachable in rules
    assert ClockSynchronized in rules
    assert TooManyOpenFilesCheck in rules
    assert SelinuxMode in rules
    assert AuditdBacklogLimit in rules
    assert VerifyDuNotHang in rules
    assert YumlockFileCheck in rules
