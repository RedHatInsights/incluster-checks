"""
Blueprint Hardware Rule.

Collects and displays hardware configuration information across nodes,
showing uniformity within node groups.
"""

from typing import List

from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.rules.hw_fw_details.collectors.cpu_collectors import (
    CpuIsolated,
    NumberOfPhysicalCoresPerProcessor,
    NumberOfThreadsPerCore,
    ProcessorCurrentFrequency,
    ProcessorType,
)
from in_cluster_checks.rules.hw_fw_details.collectors.disk_collectors import (
    DiskModel,
    DiskSize,
    DiskType,
    DiskVendor,
    OperatingSystemDiskName,
    OperatingSystemDiskSize,
    OperatingSystemDiskType,
)
from in_cluster_checks.rules.hw_fw_details.collectors.memory_collectors import (
    MemorySize,
    MemorySpeed,
    MemoryTotalSize,
    MemoryType,
)
from in_cluster_checks.rules.hw_fw_details.collectors.nic_collectors import (
    NICDriver,
    NICFirmware,
    NICModel,
    NICPortsAmount,
    NICPortsNames,
    NICSpeed,
    NICVendor,
    NICVersion,
)
from in_cluster_checks.rules.hw_fw_details.collectors.numa_collectors import NumaCpus, NumaNICs, NumaSizeMemory
from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwRule


class HardwareDetailsRule(HwFwRule):
    """
    Blueprint Hardware Rule - Informational display of hardware configuration.

    Collects hardware information (CPU, memory, NICs, disks, etc.) and shows
    uniformity within node groups. This is informational only - always returns INFO status.
    """

    unique_name = "hardware_details"
    title = "Hardware Details"

    def get_data_collectors(self) -> List[type]:
        """Get list of hardware data collectors."""
        return [
            # CPU/Processor collectors
            ProcessorType,
            ProcessorCurrentFrequency,
            NumberOfThreadsPerCore,
            NumberOfPhysicalCoresPerProcessor,
            CpuIsolated,
            # Memory collectors
            MemorySize,
            MemoryType,
            MemorySpeed,
            MemoryTotalSize,
            # NIC collectors
            NICVendor,
            NICModel,
            NICSpeed,
            NICPortsAmount,
            NICPortsNames,
            NICVersion,
            NICFirmware,
            NICDriver,
            # Disk collectors
            DiskType,
            DiskModel,
            DiskVendor,
            DiskSize,
            # OS Disk collectors
            OperatingSystemDiskName,
            OperatingSystemDiskType,
            OperatingSystemDiskSize,
            # NUMA collectors
            NumaSizeMemory,
            NumaCpus,
            NumaNICs,
        ]

    def get_data_category_key(self) -> str:
        """Get the data category key for blueprint structure."""
        return "hardware"

    def run_rule(self) -> RuleResult:
        """
        Collect hardware data and display uniformity information.

        Returns:
            RuleResult.info() with hardware uniformity details
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
