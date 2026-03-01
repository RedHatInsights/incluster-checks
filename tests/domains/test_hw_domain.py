"""Tests for HW validation domain."""

from in_cluster_checks.domains.hw_domain import HWValidationDomain
from in_cluster_checks.rules.hw.hw_validations import (
    BasicFreeMemoryValidation,
    CheckDiskUsage,
    CPUfreqScalingGovernorValidation,
    CpuSpeedValidation,
    HwSysClockCompare,
    TemperatureValidation,
)


def test_hw_domain_name():
    """Test domain name."""
    domain = HWValidationDomain()
    assert domain.domain_name() == "hardware"


def test_hw_domain_rules():
    """Test domain returns correct rules."""
    domain = HWValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 6
    assert CheckDiskUsage in rules
    assert BasicFreeMemoryValidation in rules
    assert CPUfreqScalingGovernorValidation in rules
    assert TemperatureValidation in rules
    assert CpuSpeedValidation in rules
    assert HwSysClockCompare in rules
