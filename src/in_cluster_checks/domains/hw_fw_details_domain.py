"""
HW and Firmware Details validation domain for OpenShift cluster.

Orchestrates validators that compare hardware/firmware
configurations across nodes within the same host groups.
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.hw_fw_details.firmware_rule import FirmwareDetailsRule
from in_cluster_checks.rules.hw_fw_details.hardware_rule import HardwareDetailsRule
from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector


class HwFwDetailsValidationDomain(RuleDomain):
    """
    HW and Firmware Details validation domain.

    Compares hardware/firmware configurations across nodes within host groups.
    Validates uniformity within node groups (masters, workers, etc.).
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "hw_and_firmware_details"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of hardware/firmware rules to run.

        Returns:
            List of HwFwRule classes
        """
        return [
            HardwareDetailsRule,
            FirmwareDetailsRule,
        ]

    def clean_domain(self):
        HwFwDataCollector.clear_cache()
