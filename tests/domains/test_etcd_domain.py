"""Tests for Etcd validation domain."""

from in_cluster_checks.domains.etcd_domain import EtcdValidationDomain
from in_cluster_checks.rules.etcd.etcd_validations import (
    EtcdAlarmCheck,
    EtcdBackendCommitPerformanceCheck,
    EtcdBasicCheck,
    EtcdEndpointHealthCheck,
    EtcdLeaderCheck,
    EtcdMemberCountCheck,
    EtcdWalFsyncPerformanceCheck,
    EtcdWriteReadCycleCheck,
)


def test_etcd_domain_name():
    """Test domain name."""
    domain = EtcdValidationDomain()
    assert domain.domain_name() == "etcd"


def test_etcd_domain_rules():
    """Test domain returns correct rules."""
    domain = EtcdValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 8
    assert EtcdBasicCheck in rules
    assert EtcdAlarmCheck in rules
    assert EtcdMemberCountCheck in rules
    assert EtcdLeaderCheck in rules
    assert EtcdEndpointHealthCheck in rules
    assert EtcdWriteReadCycleCheck in rules
    assert EtcdWalFsyncPerformanceCheck in rules
    assert EtcdBackendCommitPerformanceCheck in rules
