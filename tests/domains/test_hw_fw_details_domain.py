"""Tests for HW and Firmware Details validation domain."""

from unittest.mock import Mock

from in_cluster_checks.domains.hw_fw_details_domain import HwFwDetailsValidationDomain
from in_cluster_checks.rules.hw_fw_details.firmware_rule import FirmwareDetailsRule
from in_cluster_checks.rules.hw_fw_details.hardware_rule import HardwareDetailsRule


def test_hw_fw_details_domain_name():
    """Test domain name."""
    domain = HwFwDetailsValidationDomain()
    assert domain.domain_name() == "hw_and_firmware_details"


def test_hw_fw_details_domain_rules():
    """Test domain returns correct rules."""
    domain = HwFwDetailsValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 2
    assert HardwareDetailsRule in rules
    assert FirmwareDetailsRule in rules
