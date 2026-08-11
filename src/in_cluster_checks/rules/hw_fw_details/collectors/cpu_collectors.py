"""
CPU/Processor data collectors for Blueprint.

Collects CPU/Processor information from nodes following HealthChecks Blueprint pattern.
"""

import re
from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class ProcessorType(HwFwDataCollector):
    """
    Collect processor type/model from nodes.
    Follows HC Blueprint pattern: Processor@type
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "processor_type"
    title = "Processor Type"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Processor@type"

    def get_component_ids(self) -> List[str]:
        """
        Get processor IDs from dmidecode Socket Designation.
        Falls back to socket count from lscpu if dmidecode not available.

        Returns:
            List of processor IDs like ["CPU0", "CPU1"] or ["socket_0", "socket_1"]
        """
        # Try to get socket designations from dmidecode
        dmidecode_output = self._run_cached_command(SafeCmdString("sudo dmidecode -t processor"), timeout=30)

        # Parse Socket Designation fields
        socket_designations = re.findall(r"Socket Designation:\s+(.+)", dmidecode_output)
        if socket_designations:
            return socket_designations

        # Fallback: use lscpu to get socket count
        lscpu_output = self._run_cached_command(SafeCmdString("lscpu"))
        socket_match = re.search(r"Socket\(s\):\s+(\d+)", lscpu_output)
        socket_count = int(socket_match.group(1)) if socket_match else 1

        return [f"socket_{i}" for i in range(socket_count)]

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect processor type/model for each processor.

        Returns:
            Dictionary of {processor_id: model_name}
            Example: {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"}
        """
        # Get lscpu output (cached)
        lscpu_output = self._run_cached_command(SafeCmdString("lscpu"))

        # Parse model name
        model_match = re.search(r"Model name:\s+(.+)", lscpu_output)
        if not model_match:
            return {processor_id: "Unknown" for processor_id in self.get_component_ids()}

        # Clean up model name (remove frequency, parentheses)
        model_name = model_match.group(1).strip()
        model_name = model_name.split("@")[0].strip()  # Remove frequency
        model_name = re.sub(r"\([^)]*\)", "", model_name).strip()  # Remove parentheses

        # Return same model for all processor IDs (all sockets have same CPU)
        return {processor_id: model_name for processor_id in self.get_component_ids()}


class ProcessorCurrentFrequency(HwFwDataCollector):
    """
    Collect current processor frequency from nodes.
    Follows HC Blueprint pattern: Processor@frequency_in_mhz
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "processor_current_frequency"
    title = "Processor Current Frequency"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Processor@frequency_in_mhz"

    def get_component_ids(self) -> List[str]:
        """Get processor IDs (reuses ProcessorType logic)."""
        return ProcessorType(self._host_executor).get_component_ids()

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect current processor frequency for each processor.

        Returns:
            Dictionary of {processor_id: frequency_in_mhz}
            Example: {"CPU0": 2100, "CPU1": 2100}
        """
        dmidecode_output = self._run_cached_command(SafeCmdString("sudo dmidecode -t processor"), timeout=30)

        # Parse processor information as JSON-like blocks
        processors_info = self._parse_dmidecode_processor_blocks(dmidecode_output)

        # Get frequency by socket designation
        frequency_by_socket = {}
        for proc_info in processors_info:
            socket_designation = proc_info.get("Socket Designation", "").strip()
            current_speed = proc_info.get("Current Speed", "").strip()

            if socket_designation and current_speed:
                # Parse frequency from "2100 MHz" format
                freq_match = re.search(r"(\d+)\s*MHz", current_speed)
                if freq_match:
                    frequency_by_socket[socket_designation] = int(freq_match.group(1))

        # Map to component IDs
        component_ids = self.get_component_ids()
        result = {}
        for comp_id in component_ids:
            # If component ID matches socket designation, use it
            freq = frequency_by_socket.get(comp_id)
            if freq is None:
                # Fallback: use first frequency found (all sockets typically same)
                freq = next(iter(frequency_by_socket.values()), 0)
            result[comp_id] = freq

        return result

    def _parse_dmidecode_processor_blocks(self, output: str) -> List[Dict[str, str]]:
        """
        Parse dmidecode processor output into list of dicts.

        Args:
            output: Raw dmidecode output

        Returns:
            List of processor info dicts with fields like "Socket Designation", "Current Speed"
        """
        processors = []
        current_block = {}
        in_processor_block = False

        for line in output.splitlines():
            line = line.strip()

            # Detect start of processor block
            if line.startswith("Processor Information"):
                in_processor_block = True
                current_block = {}
                continue

            # Detect end of block (empty line or new block)
            if in_processor_block and (not line or line.startswith("Handle")):
                if current_block:
                    processors.append(current_block)
                    current_block = {}
                in_processor_block = False
                continue

            # Parse key-value pairs
            if in_processor_block and ":" in line:
                key, value = line.split(":", 1)
                current_block[key.strip()] = value.strip()

        # Don't forget last block
        if current_block:
            processors.append(current_block)

        return processors


class NumberOfThreadsPerCore(HwFwDataCollector):
    """
    Collect number of threads per core.
    Follows HC Blueprint pattern: Processor@number_of_threads_per_core
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "processor_threads_per_core"
    title = "Threads Per Core"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Processor@number_of_threads_per_core"

    def get_component_ids(self) -> List[str]:
        """Get processor IDs (reuses ProcessorType logic)."""
        return ProcessorType(self._host_executor).get_component_ids()

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect threads per core (applies to all processors).

        Returns:
            Dictionary of {processor_id: threads_per_core}
            Example: {"CPU0": 2, "CPU1": 2}
        """
        lscpu_output = self._run_cached_command(SafeCmdString("lscpu"))

        # Parse threads per core
        threads_match = re.search(r"Thread\(s\) per core:\s+(\d+)", lscpu_output)
        threads_per_core = int(threads_match.group(1)) if threads_match else 1

        # Return same value for all processors
        return {processor_id: threads_per_core for processor_id in self.get_component_ids()}


class NumberOfPhysicalCoresPerProcessor(HwFwDataCollector):
    """
    Collect number of physical cores per processor socket.
    Follows HC Blueprint pattern: Processor@number_of_physical_cores_per_processor
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "processor_physical_cores"
    title = "Physical Cores Per Processor"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Processor@number_of_physical_cores_per_processor"

    def get_component_ids(self) -> List[str]:
        """Get processor IDs (reuses ProcessorType logic)."""
        return ProcessorType(self._host_executor).get_component_ids()

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect physical cores per processor socket.

        Returns:
            Dictionary of {processor_id: physical_cores_per_socket}
            Example: {"CPU0": 22, "CPU1": 22}
        """
        lscpu_output = self._run_cached_command(SafeCmdString("lscpu"))

        # Parse cores per socket
        cores_match = re.search(r"Core\(s\) per socket:\s+(\d+)", lscpu_output)
        cores_per_socket = int(cores_match.group(1)) if cores_match else 1

        # Return same value for all processors
        return {processor_id: cores_per_socket for processor_id in self.get_component_ids()}


class CpuIsolated(HwFwDataCollector):
    """
    Collect CPU isolation configuration from nodes.
    Follows HC Blueprint pattern: CPU@isolated

    Note: This is optional and deployment-specific. Some OpenShift deployments
    use CPU isolation for performance tuning (typically on workers/edges).
    If no isolation is configured, returns empty string.

    The isolcpus parameter may include prefixes like "managed_irq" which are
    filtered out to return only the actual CPU numbers.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "cpu_isolated"
    title = "CPU Isolation"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "CPU@isolated"

    def get_component_ids(self) -> List[str]:
        """Single component since isolation applies to the node as a whole."""
        return ["1"]

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect isolated CPU list from kernel command line.

        Returns:
            Dictionary with isolated CPU list as comma-separated string.
            Example: {"1": "3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, ..."} if isolated
            Example: {"1": ""} if no isolation configured
        """
        # Read kernel command line
        cmdline_output = self._run_cached_command(SafeCmdString("cat /proc/cmdline"))

        # Check if isolcpus parameter exists
        if " isolcpus=" not in cmdline_output:
            # No CPU isolation configured
            return {"1": ""}

        # Parse isolcpus parameter value
        # Example: "isolcpus=managed_irq,3-31,34-63,67-95,98-127"
        # Example: "isolcpus=2-8,10-14"
        isolcpus_str = cmdline_output.split(" isolcpus=")[1].split(" ")[0]

        # Parse CPU ranges and individual CPUs
        isolated_cpus = self._parse_cpu_list(isolcpus_str)

        # Return as comma-separated string
        return {"1": ", ".join(str(cpu) for cpu in isolated_cpus)}

    def _parse_cpu_list(self, cpu_spec: str) -> List[int]:
        """
        Parse CPU list specification into individual CPU numbers.
        Follows HealthChecks _separate_the_range() logic.

        Args:
            cpu_spec: CPU specification like "managed_irq,2-8,10-14" or "2,3,4,10,11"

        Returns:
            Sorted list of individual CPU numbers
            Example: [2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14]
        """
        pure_comma_lst = []  # Individual CPU numbers
        lst_with_dash = []  # CPU ranges to expand

        # Split by comma and categorize
        for part in cpu_spec.split(","):
            part = part.strip()

            if "-" in part:
                # Range like "2-8" - add to list for expansion
                lst_with_dash.append(part)
            else:
                # Individual number or non-numeric (like "managed_irq")
                if part != "managed_irq":  # Explicitly filter HC-known prefix
                    try:
                        pure_comma_lst.append(int(part))
                    except ValueError:
                        # Skip non-numeric values
                        continue

        # Expand ranges
        for range_spec in lst_with_dash:
            try:
                start, end = range_spec.split("-")
                pure_comma_lst.extend(range(int(start), int(end) + 1))
            except ValueError:
                # Skip malformed ranges
                continue

        return sorted(pure_comma_lst)
