"""
Memory data collectors for Blueprint.

Collects memory information from nodes following HealthChecks Blueprint pattern.
Based on HC flows/Blueprint/BlueprintDataCollectors.py Memory classes.
"""

import re
from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class Memory(HwFwDataCollector):
    """Base class for memory data collectors."""

    objective_hosts = [Objectives.ALL_NODES]

    def get_component_ids(self) -> List[str]:
        """
        Get memory module locators (populated slots only).
        Follows HC pattern: filter out "No Module Installed".

        Returns:
            List of memory locators like ["DIMM_A1", "DIMM_A2", ...]
        """
        memory_info = self._filter_valid_memory_from_dmidecode()
        locators = []

        for mem_dict in memory_info:
            locator = mem_dict.get("Locator", "").strip()
            if locator:
                locators.append(locator)

        return locators if locators else ["DIMM_0"]  # Fallback

    def _filter_valid_memory_from_dmidecode(self) -> List[Dict[str, str]]:
        """
        Get dmidecode memory info and filter out empty slots.
        Follows HC pattern from Memory.filter_valid_memory_from_dmidecode_json().

        Returns:
            List of memory device dicts (only populated slots)
        """
        dmidecode_output = self._run_cached_command(SafeCmdString("sudo dmidecode -t memory"), timeout=30)
        dmidecode_json = self._parse_dmidecode_memory_blocks(dmidecode_output)

        res = []
        for memory_dict in dmidecode_json:
            size = memory_dict.get("Size", "").strip()
            if size and size != "No Module Installed":
                res.append(memory_dict)

        return res

    def _parse_dmidecode_memory_blocks(self, output: str) -> List[Dict[str, str]]:
        """
        Parse dmidecode memory output into list of dicts.

        Args:
            output: Raw dmidecode -t memory output

        Returns:
            List of memory device info dicts
        """
        devices = []
        current_block = {}
        in_memory_block = False

        for line in output.splitlines():
            line_stripped = line.strip()

            # Detect start of memory device block
            if line_stripped.startswith("Memory Device"):
                in_memory_block = True
                current_block = {}
                continue

            # Detect end of block (empty line or new handle)
            if in_memory_block and (not line_stripped or line_stripped.startswith("Handle")):
                if current_block:
                    devices.append(current_block)
                    current_block = {}
                in_memory_block = False
                continue

            # Parse key-value pairs
            if in_memory_block and ":" in line_stripped:
                key, value = line_stripped.split(":", 1)
                current_block[key.strip()] = value.strip()

        # Don't forget last block
        if current_block:
            devices.append(current_block)

        return devices


class MemorySize(Memory):
    """
    Collect memory module sizes.
    Follows HC Blueprint pattern: Memory@size_in_mb
    """

    unique_name = "memory_size"
    title = "Memory Size"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Memory@size_in_mb"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect memory size for each module.
        Follows HC Memory.get_memory_size() pattern.

        Returns:
            Dictionary of {locator: size_in_mb}
            Example: {"DIMM_A1": 32768, "DIMM_A2": 32768}
        """
        memory_info = self._filter_valid_memory_from_dmidecode()

        # Get locator -> size mapping
        sizes_with_suffix = {}
        for mem_dict in memory_info:
            locator = mem_dict.get("Locator", "").strip()
            size = mem_dict.get("Size", "").strip()
            if locator and size:
                sizes_with_suffix[locator] = size

        # Convert to numeric (MB)
        return self._set_dict_values_to_numeric(sizes_with_suffix, "MB")

    def _set_dict_values_to_numeric(self, values_dict: Dict[str, str], unit: str) -> Dict[str, int]:
        """
        Convert size strings to numeric MB values.
        Follows HC pattern from BlueprintDataCollector.set_dict_values_to_numeric().

        Args:
            values_dict: {id: "32 GB"} or {id: "32768 MB"}
            unit: Expected unit suffix ('MB', 'GB')

        Returns:
            {id: numeric_value_in_mb}
        """
        result = {}

        for key, value_str in values_dict.items():
            # Parse number and unit from string like "32 GB" or "32768 MB"
            match = re.search(r"(\d+)\s*(GB|MB|TB)", value_str, re.IGNORECASE)
            if not match:
                result[key] = 0
                continue

            number = int(match.group(1))
            found_unit = match.group(2).upper()

            # Convert to MB
            if found_unit == "GB":
                result[key] = number * 1024
            elif found_unit == "TB":
                result[key] = number * 1024 * 1024
            else:  # MB
                result[key] = number

        return result


class MemoryType(Memory):
    """
    Collect memory type (DDR4, DDR5, etc.).
    Follows HC Blueprint pattern: Memory@type
    """

    unique_name = "memory_type"
    title = "Memory Type"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Memory@type"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect memory type for each module.
        Follows HC MemoryType.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {locator: type}
            Example: {"DIMM_A1": "DDR4", "DIMM_A2": "DDR4"}
        """
        memory_info = self._filter_valid_memory_from_dmidecode()

        result = {}
        for mem_dict in memory_info:
            locator = mem_dict.get("Locator", "").strip()
            mem_type = mem_dict.get("Type", "Unknown").strip()
            if locator:
                result[locator] = mem_type

        return result if result else {"DIMM_0": "Unknown"}


class MemorySpeed(Memory):
    """
    Collect memory speed in MHz.
    Follows HC Blueprint pattern: Memory@speed_in_mhz
    """

    unique_name = "memory_speed"
    title = "Memory Speed"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Memory@speed_in_mhz"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect memory speed for each module.
        Follows HC MemorySpeed.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {locator: speed_in_mhz}
            Example: {"DIMM_A1": 3200, "DIMM_A2": 3200}
        """
        memory_info = self._filter_valid_memory_from_dmidecode()

        # Get locator -> speed mapping
        speeds_with_suffix = {}
        for mem_dict in memory_info:
            locator = mem_dict.get("Locator", "").strip()
            speed = mem_dict.get("Speed", "").strip()
            if locator and speed:
                speeds_with_suffix[locator] = speed

        # Convert to numeric (MHz) - HC uses MT/s which is equivalent to MHz for DDR
        return self._set_dict_values_to_numeric_speed(speeds_with_suffix)

    def _set_dict_values_to_numeric_speed(self, values_dict: Dict[str, str]) -> Dict[str, int]:
        """
        Convert speed strings to numeric MHz values.
        Follows HC pattern - handles both MT/s and MHz.

        Args:
            values_dict: {id: "3200 MT/s"} or {id: "3200 MHz"}

        Returns:
            {id: numeric_value_in_mhz}
        """
        result = {}

        for key, value_str in values_dict.items():
            # Parse number and unit from string like "3200 MT/s" or "3200 MHz"
            match = re.search(r"(\d+)\s*(?:MT/s|MHz)", value_str, re.IGNORECASE)
            if match:
                result[key] = int(match.group(1))
            else:
                result[key] = 0

        return result


class MemoryTotalSize(Memory):
    """
    Collect total memory size across all modules.
    Follows HC Blueprint pattern: Total memory@total_size_in_mb
    """

    unique_name = "memory_total_size"
    title = "Total Memory Size"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Total memory@total_size_in_mb"

    def get_component_ids(self) -> List[str]:
        """Single ID for total (matches HC pattern)."""
        return ["Total of all units"]

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect total memory size.
        Follows HC MemoryTotalSize.collect_blueprint_data() pattern.

        Returns:
            Dictionary with total size
            Example: {"Total of all units": 131072}
        """
        # Get individual memory sizes using MemorySize collector
        memory_size_collector = MemorySize(self._host_executor)
        id_memory_size_dict = memory_size_collector.collect_data()

        # Sum all sizes
        total_size = sum(id_memory_size_dict.values())

        return {"Total of all units": total_size}
