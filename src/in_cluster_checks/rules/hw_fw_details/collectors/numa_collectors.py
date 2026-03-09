"""
NUMA (Non-Uniform Memory Access) data collectors for Blueprint hardware validation.

Collects NUMA node configuration (memory size, CPU affinity, NIC affinity).
Based on HealthChecks NUMABlueprintDataCollectors pattern.
"""

import re
from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class NUMADataCollector(HwFwDataCollector):
    """
    Base class for NUMA data collectors.

    Provides shared logic for getting NUMA node IDs.
    All NUMA collectors inherit from this class.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def get_component_ids(self) -> List[str]:
        """
        Get NUMA node IDs from lscpu.

        Returns:
            List of NUMA node IDs (e.g., ["node 0", "node 1"])
        """
        cmd = SafeCmdString("lscpu | grep 'NUMA node(s):'")
        output = self._run_cached_command(cmd, timeout=30)

        # Parse number of NUMA nodes
        match = re.search(r"NUMA node\(s\):\s+(\d+)", output)
        if not match:
            return []

        num_nodes = int(match.group(1))
        return [f"node {i}" for i in range(num_nodes)]

    def get_objective_name(self) -> str:
        """Get blueprint objective name - override in subclass."""
        return "Numa@unknown"


class NumaSizeMemory(NUMADataCollector):
    """
    Collect memory size per NUMA node.

    Uses sysfs to get memory info for each NUMA node.
    Follows HC Blueprint pattern: Numa@total_allocated_memory_in_mb
    """

    unique_name = "numa_size_memory"
    title = "NUMA Memory Size"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Numa@total_allocated_memory_in_mb"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect total allocated memory size for each NUMA node.

        Uses /sys/devices/system/node/nodeX/meminfo to get MemTotal.

        Returns:
            Dictionary of {numa_id: memory_in_mb}
            Example: {"node 0": 32768, "node 1": 32768}
        """
        result = {}

        for numa_id in self.get_component_ids():
            # Extract node number from "node X" format
            node_num = numa_id.split()[-1]

            # Read meminfo from sysfs
            cmd = SafeCmdString("cat /sys/devices/system/node/node{node_num}/meminfo").format(node_num=node_num)

            try:
                output = self._run_cached_command(cmd, timeout=30)

                # Parse MemTotal line
                # Format: "Node X MemTotal:       32948232 kB"
                match = re.search(r"MemTotal:\s+(\d+)\s+kB", output)
                if match:
                    memory_kb = int(match.group(1))
                    memory_mb = memory_kb // 1024
                    result[numa_id] = memory_mb
                else:
                    result[numa_id] = 0
            except Exception:
                # If sysfs not available or error, return 0
                result[numa_id] = 0

        return result


class NumaCpus(NUMADataCollector):
    """
    Collect CPU list per NUMA node.

    Uses lscpu to get CPU affinity for each NUMA node.
    Follows HC Blueprint pattern: Numa@cpus_per_numa
    """

    unique_name = "numa_cpus"
    title = "NUMA CPUs"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Numa@cpus_per_numa"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect CPU list for each NUMA node.

        Uses lscpu to get NUMA node CPU lists.

        Returns:
            Dictionary of {numa_id: cpu_list}
            Example: {"node 0": "0-15,32-47", "node 1": "16-31,48-63"}
        """
        cmd = SafeCmdString("lscpu")
        output = self._run_cached_command(cmd, timeout=30)

        result = {}

        for numa_id in self.get_component_ids():
            # Extract node number from "node X" format
            node_num = numa_id.split()[-1]

            # Look for "NUMA nodeX CPU(s):" line
            # Format: "NUMA node0 CPU(s):               0-15,32-47"
            pattern = rf"NUMA node{node_num} CPU\(s\):\s+(.+)"
            match = re.search(pattern, output)

            if match:
                result[numa_id] = match.group(1).strip()
            else:
                result[numa_id] = "---"

        return result


class NumaNICs(NUMADataCollector):
    """
    Collect network interface affinity per NUMA node.

    Uses sysfs to get NIC NUMA affinity for each network interface.
    Follows HC Blueprint pattern: Numa@nic_per_numa
    """

    unique_name = "numa_nics"
    title = "NUMA NICs"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Numa@nic_per_numa"

    def collect_data(self, **kwargs) -> Dict[str, List[str]]:
        """
        Collect network interface list for each NUMA node.

        Uses /sys/class/net/*/device/numa_node to get NIC NUMA affinity.
        Only includes physical network interfaces (not virtual/loopback).

        Returns:
            Dictionary of {numa_id: [list of port names]}
            Example: {"node 0": ["ens1f0np0", "ens1f1np1"], "node 1": ["ens2f0np0", "ens2f1np1"]}
        """
        # Initialize result with empty lists for each NUMA node
        numa_ids = self.get_component_ids()
        result = {numa_id: [] for numa_id in numa_ids}

        # Get prefix for NUMA IDs (e.g., "node " from "node 0")
        if numa_ids:
            prefix = numa_ids[0].rsplit(None, 1)[0] + " "
        else:
            prefix = "node "

        # Get list of all network interfaces with physical devices (those with np in name)
        cmd = SafeCmdString("ls /sys/class/net/ | grep np")
        try:
            output = self._run_cached_command(cmd, timeout=30)
            all_port_names = [line.strip() for line in output.splitlines() if line.strip()]
        except Exception:
            # If command fails, return empty result
            return result

        # Check each port's NUMA affinity
        for port_name in all_port_names:
            numa_node_path = f"/sys/class/net/{port_name}/device/numa_node"

            try:
                # Read NUMA node number
                cmd = SafeCmdString("cat {numa_node_path}").format(numa_node_path=numa_node_path)
                output = self._run_cached_command(cmd, timeout=30)

                # Parse NUMA node number (use abs() to handle -1 for non-NUMA systems)
                numa_node_num = abs(int(output.strip()))
                numa_id = f"{prefix}{numa_node_num}"

                # Add port to corresponding NUMA node
                if numa_id in result:
                    result[numa_id].append(port_name)

            except Exception:
                # If sysfs not available or error, skip this port
                continue

        return result
