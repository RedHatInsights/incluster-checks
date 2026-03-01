"""
Blueprint Firmware Rule.

Collects and displays firmware/BIOS information across nodes,
showing uniformity within node groups.
"""

from typing import List

from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.rules.hw_fw_details.collectors.bios_collectors import (
    BIOSFirmware,
    BIOSReleaseDate,
    BIOSRevision,
    BIOSVersion,
)
from in_cluster_checks.rules.hw_fw_details.collectors.os_collectors import KernelVersion, OperatingSystemVersion
from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwRule


class FirmwareDetailsRule(HwFwRule):
    """
    Blueprint Firmware Rule - Informational display of firmware/BIOS configuration.

    Collects BIOS/firmware information and shows uniformity within node groups.
    This is informational only - always returns INFO status.
    """

    unique_name = "firmware_details"
    title = "Firmware Details"

    def get_data_collectors(self) -> List[type]:
        """Get list of firmware/BIOS data collectors."""
        return [
            # OS/Kernel collectors
            OperatingSystemVersion,
            KernelVersion,
            # BIOS collectors
            BIOSVersion,
            BIOSFirmware,
            BIOSRevision,
            BIOSReleaseDate,
        ]

    def run_rule(self) -> RuleResult:
        """
        Collect firmware data and display uniformity information.

        Returns:
            RuleResult.info() with firmware uniformity details
        """
        # Group nodes by labels
        node_groups = self._group_nodes_by_labels(self._node_executors)

        self.add_to_rule_log(f"Found {len(node_groups)} node group(s) by labels:")
        for label, executors in node_groups.items():
            node_names = [e.node_name for e in executors]
            self.add_to_rule_log(f"  - '{label}': {len(executors)} node(s) - {', '.join(node_names)}")

        # Collect data from all nodes
        collected_data = self._collect_all_data(node_groups)

        # Compare within groups (implemented in base class)
        return self.compare_within_groups(collected_data, node_groups)

    def get_data_category_key(self) -> str:
        """Get the data category key for blueprint structure."""
        return "firmware"
