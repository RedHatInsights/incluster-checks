"""
Disk data collectors for Blueprint hardware validation.

Collects disk information (type, model, vendor, size) from lsblk and smartctl.
Based on HealthChecks DiskBlueprintDataCollectors pattern.
"""

import re
from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DiskDataCollector(HwFwDataCollector):
    """
    Base class for disk data collectors.

    Provides shared logic for getting disk IDs and filtering real disks.
    All disk collectors inherit from this class.
    """

    objective_hosts = [Objectives.ALL_NODES]
    REAL_DISK_PREFIXES = ["sd", "nvme", "hd"]

    def get_component_ids(self) -> List[str]:
        """
        Get disk device names from lsblk.

        Returns:
            List of disk names (e.g., ["sda", "sdb", "nvme0n1"])
            Only includes real physical disks (no virtual/loop devices)
        """
        cmd = SafeCmdString("sudo lsblk -d -o name,model")
        output = self._run_cached_command(cmd, timeout=30)

        lines = output.splitlines()
        if len(lines) < 2:  # Need header + at least one disk
            return []

        # Skip header line
        disk_lines = lines[1:]

        # Filter to real disks only
        real_disks = []
        for line in disk_lines:
            if self._is_real_disk(line):
                # Extract disk name (first column)
                disk_name = line.split()[0]
                real_disks.append(disk_name)

        return sorted(real_disks)

    def _is_real_disk(self, disk_line: str) -> bool:
        """
        Check if disk line represents a real physical disk.

        Filters out virtual disks, loop devices, network storage, etc.

        Args:
            disk_line: Line from lsblk output (format: "sda  SAMSUNG MZ7LH480")

        Returns:
            True if this is a real disk
        """
        # Must start with known disk prefix
        if not disk_line.startswith(tuple(self.REAL_DISK_PREFIXES)):
            return False

        # Exclude virtual disks
        if "Virtual" in disk_line or "virtual" in disk_line:
            return False

        # Exclude network-attached storage (SAN/NAS devices)
        # FlashArray: Pure Storage arrays
        # NETAPP: NetApp storage
        # iSCSI: iSCSI volumes
        network_storage_keywords = ["FlashArray", "NETAPP", "iSCSI", "DGC", "EMC"]
        if any(keyword in disk_line for keyword in network_storage_keywords):
            return False

        return True

    def _collect_lsblk_data(self, field_name: str, is_number: bool = False) -> Dict[str, any]:
        """
        Collect data from lsblk for specific field.

        Args:
            field_name: Field name for lsblk -o option (e.g., "model", "size", "rota")
            is_number: If True, convert values to integers

        Returns:
            Dict of {disk_name: field_value}
        """
        cmd = SafeCmdString("sudo lsblk -d -o name,{field_name}").format(field_name=field_name)
        output = self._run_cached_command(cmd, timeout=30)

        lines = output.splitlines()
        if len(lines) < 2:
            return {}

        # Skip header
        disk_lines = lines[1:]

        result = {}
        disk_ids = self.get_component_ids()

        for line in disk_lines:
            parts = line.split(None, 1)  # Split on first whitespace
            if len(parts) < 2:
                # No value, just disk name
                if len(parts) == 1:
                    disk_name = parts[0]
                    if disk_name in disk_ids:
                        result[disk_name] = "----" if not is_number else 0
                continue

            disk_name, value = parts
            if disk_name not in disk_ids:
                continue

            value = value.strip()

            if is_number:
                # Extract numeric value (handle units like "1T", "500G")
                numeric_match = re.search(r"(\d+)", value)
                if numeric_match:
                    result[disk_name] = int(numeric_match.group(1))
                else:
                    result[disk_name] = 0
            else:
                result[disk_name] = value if value else "----"

        return result

    def get_objective_name(self) -> str:
        """Get blueprint objective name - override in subclass."""
        return "Disk@unknown"


class DiskType(DiskDataCollector):
    """
    Collect disk type (HDD/SSD/NVMe).

    Uses lsblk rota field and smartctl to determine disk type.
    Follows HC Blueprint pattern: Disk@type
    """

    unique_name = "disk_type"
    title = "Disk Type"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Disk@type"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect disk type for each disk.

        Returns:
            Dictionary of {disk_name: type}
            Example: {"sda": "HDD", "sdb": "SSD", "nvme0n1": "NVMe"}
        """
        # Get rotation flag (1 = HDD, 0 = SSD/NVMe)
        rota_data = self._collect_lsblk_data("rota", is_number=True)

        result = {}
        for disk_name, rota_value in rota_data.items():
            if rota_value == 1:
                result[disk_name] = "HDD"
            elif rota_value == 0:
                # SSD or NVMe - check with smartctl
                disk_type = self._find_specific_ssd_type(disk_name)
                result[disk_name] = disk_type
            else:
                result[disk_name] = "Unknown"

        return result

    def _find_specific_ssd_type(self, disk_name: str) -> str:
        """
        Determine if SSD is NVMe or regular SSD.

        Args:
            disk_name: Disk device name

        Returns:
            "NVMe" or "SSD"
        """
        # NVMe disks have nvme in name
        if "nvme" in disk_name:
            return "NVMe"

        # Use smartctl to check (cached, ignore errors as smartctl returns 64 for old SMART data)
        cmd = SafeCmdString("sudo smartctl -a /dev/{disk_name}").format(disk_name=disk_name)
        output = self._run_cached_command(cmd, timeout=30, ignore_errors=True)

        # Check for NVMe indicators in output
        if "Total NVM Capacity:" in output or "NVMe" in output:
            return "NVMe"

        return "SSD"


class DiskModel(DiskDataCollector):
    """
    Collect disk model information.

    Uses lsblk to get model for each disk.
    Follows HC Blueprint pattern: Disk@model
    """

    unique_name = "disk_model"
    title = "Disk Model"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Disk@model"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect disk model for each disk.

        Returns:
            Dictionary of {disk_name: model}
            Example: {"sda": "SAMSUNG MZ7LH960", "nvme0n1": "INTEL SSDPE2KX040T8"}
        """
        return self._collect_lsblk_data("model")


class DiskVendor(DiskDataCollector):
    """
    Collect disk vendor information.

    Uses lsblk vendor field, falls back to model if vendor not available.
    Follows HC Blueprint pattern: Disk@vendor
    """

    unique_name = "disk_vendor"
    title = "Disk Vendor"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Disk@vendor"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect disk vendor for each disk.

        Falls back to model if vendor field is empty.

        Returns:
            Dictionary of {disk_name: vendor}
            Example: {"sda": "SAMSUNG", "nvme0n1": "INTEL"}
        """
        vendors = self._collect_lsblk_data("vendor")
        models = self._collect_lsblk_data("model")

        # Use model as fallback if vendor is missing
        for disk_name, vendor in vendors.items():
            if vendor == "----" or not vendor:
                vendors[disk_name] = models.get(disk_name, "----")

        return vendors


class DiskSize(DiskDataCollector):
    """
    Collect disk size in MB.

    Uses lsblk to get size for each disk.
    Follows HC Blueprint pattern: Disk@size_in_mb
    """

    unique_name = "disk_size"
    title = "Disk Size"
    BYTES_IN_MB = 1024**2

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Disk@size_in_mb"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect disk size in MB for each disk.

        Returns:
            Dictionary of {disk_name: size_in_mb}
            Example: {"sda": 960197, "nvme0n1": 3840755}
        """
        # Get size in bytes
        cmd = SafeCmdString("sudo lsblk -d -o name,size -b")
        output = self._run_cached_command(cmd, timeout=30)

        lines = output.splitlines()
        if len(lines) < 2:
            return {}

        disk_lines = lines[1:]
        disk_ids = self.get_component_ids()

        result = {}
        for line in disk_lines:
            parts = line.split()
            if len(parts) < 2:
                continue

            disk_name, size_bytes_str = parts[0], parts[1]

            if disk_name not in disk_ids:
                continue

            try:
                size_bytes = int(size_bytes_str)
                size_mb = size_bytes // self.BYTES_IN_MB
                result[disk_name] = size_mb
            except ValueError:
                result[disk_name] = 0

        return result


class OperatingSystemDisk(DiskDataCollector):
    """
    Base class for operating system disk collectors.

    These collectors identify and collect information about the disk(s)
    used for the root filesystem (/).

    Inherits from DiskDataCollector to reuse disk identification and filtering logic.
    """

    def get_component_ids(self) -> List[str]:
        """
        Get component ID for OS disk collector.

        Returns:
            Single-item list with ID "operating_system_disk"
        """
        return ["operating_system_disk"]

    def get_topic(self) -> str:
        """Get blueprint topic name."""
        return "operating_system_disk"

    @staticmethod
    def _get_separator() -> str:
        """Get separator for joining multiple disk values."""
        return " "

    def _get_os_disk_names(self, **kwargs) -> List[str]:
        """
        Get list of OS disk names (shared helper method).

        Returns:
            List of disk names (e.g., ["sda"] or ["sda", "sdb"])
            Empty list if no OS disks found
        """
        cmd = SafeCmdString("sudo lsblk -n")
        output = self._run_cached_command(cmd, timeout=30)
        return self._parse_lsblk_output(output)

    def _parse_lsblk_output(self, output: str) -> List[str]:
        """
        Parse lsblk output to find physical disks containing root filesystem.

        Algorithm (from HealthChecks):
        1. Process lines sequentially
        2. Lines ending with "disk" are physical disks (no special chars at start)
        3. Lines ending with "/" or "/sysroot" are root filesystem mounts
        4. When we find "/" or "/sysroot", the current physical_disk is an OS disk
        5. This works because lsblk shows parent disks before their volumes

        Note: In RHCOS (Red Hat CoreOS), the root filesystem is mounted at /sysroot,
        not /, so we need to check for both.

        Args:
            output: Output from "lsblk -n" command

        Returns:
            Sorted list of physical disk names (e.g., ["sda"] or ["sda", "sdb"])
        """
        out_lines = [x.strip() for x in output.splitlines()]
        physical_disks = []
        current_physical_disk = ""

        for line in out_lines:
            # Physical disks end with "disk" and have no leading special chars
            if line.endswith("disk"):
                # Extract disk name (first column)
                current_physical_disk = line.split()[0]

            # Root filesystem mount points end with "/" or "/sysroot" (RHCOS)
            if line.endswith("/") or line.endswith("/sysroot"):
                # This partition/volume is on current_physical_disk
                if current_physical_disk and current_physical_disk not in physical_disks:
                    physical_disks.append(current_physical_disk)

        return sorted(physical_disks)

    def _get_all_disk_types(self, **kwargs) -> Dict[str, str]:
        """
        Get disk types for all disks (shared helper method).

        Reuses parent class's get_component_ids() to get real disk names,
        then determines type from lsblk rota field.

        Returns:
            Dict of {disk_name: disk_type}
        """
        # Use parent's get_component_ids() to get real disk names
        real_disk_names = super().get_component_ids()

        # Collect disk rotation data (0=SSD, 1=HDD)
        cmd = SafeCmdString("sudo lsblk -d -o name,rota")
        output = self._run_cached_command(cmd, timeout=30)

        lines = output.splitlines()
        if len(lines) < 2:
            return {}

        # Skip header
        disk_lines = lines[1:]

        result = {}

        for line in disk_lines:
            parts = line.split()
            if len(parts) < 2:
                continue

            disk_name = parts[0]
            if disk_name not in real_disk_names:
                continue

            rota = parts[1]

            # Determine disk type
            if disk_name.startswith("nvme"):
                disk_type = "NVMe"
            elif rota == "0":
                disk_type = "SSD"
            elif rota == "1":
                disk_type = "HDD"
            else:
                disk_type = "----"

            result[disk_name] = disk_type

        return result

    def _get_all_disk_sizes(self, **kwargs) -> Dict[str, int]:
        """
        Get disk sizes for all disks in MB (shared helper method).

        Reuses parent class's get_component_ids() to get real disk names,
        then gets sizes from lsblk.

        Returns:
            Dict of {disk_name: size_in_mb}
        """
        # Use parent's get_component_ids() to get real disk names
        real_disk_names = super().get_component_ids()

        cmd = SafeCmdString("sudo lsblk -d -o name,size -b")
        output = self._run_cached_command(cmd, timeout=30)

        lines = output.splitlines()
        if len(lines) < 2:
            return {}

        # Skip header
        disk_lines = lines[1:]

        result = {}

        for line in disk_lines:
            parts = line.split()
            if len(parts) < 2:
                continue

            disk_name = parts[0]
            if disk_name not in real_disk_names:
                continue

            size_bytes = parts[1]

            # Convert bytes to MB
            try:
                size_mb = int(size_bytes) // (1024 * 1024)
                result[disk_name] = size_mb
            except (ValueError, ZeroDivisionError):
                result[disk_name] = 0

        return result


class OperatingSystemDiskName(OperatingSystemDisk):
    """
    Collect name(s) of disk(s) used for root filesystem.

    Uses lsblk to identify which physical disk(s) contain partitions/volumes
    mounted at / (root). Handles single disk, RAID, LVM, and multipath configs.

    Follows HC Blueprint pattern: operating_system_disk@name
    """

    unique_name = "operating_system_disk_name"
    title = "Operating System Disk Name"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return f"{self.get_topic()}@name"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect OS disk name(s).

        Returns:
            Dictionary with single key "operating_system_disk"
            Value is space-separated disk names (e.g., "sda" or "sda sdb")
        """
        physical_disks = self._get_os_disk_names(**kwargs)
        disk_names = self._get_separator().join(physical_disks)

        return {"operating_system_disk": disk_names}


class OperatingSystemDiskType(OperatingSystemDisk):
    """
    Collect type(s) of disk(s) used for root filesystem.

    Uses shared helper methods to find OS disks and look up their types.

    Follows HC Blueprint pattern: operating_system_disk@type
    """

    unique_name = "operating_system_disk_type"
    title = "Operating System Disk Type"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return f"{self.get_topic()}@type"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect OS disk type(s).

        Returns:
            Dictionary with single key "operating_system_disk"
            Value is space-separated disk types (e.g., "SSD" or "SSD HDD")
        """
        # Get OS disk names using shared helper
        os_disk_names = self._get_os_disk_names(**kwargs)

        if not os_disk_names:
            return {"operating_system_disk": "----"}

        # Get all disk types using shared helper
        all_disk_types = self._get_all_disk_types(**kwargs)

        # Lookup types for OS disks
        os_disk_types = [str(all_disk_types.get(disk, "----")) for disk in os_disk_names]

        return {"operating_system_disk": self._get_separator().join(os_disk_types)}


class OperatingSystemDiskSize(OperatingSystemDisk):
    """
    Collect size(s) of disk(s) used for root filesystem.

    Uses shared helper methods to find OS disks and look up their sizes.

    Follows HC Blueprint pattern: operating_system_disk@size_in_mb
    """

    unique_name = "operating_system_disk_size"
    title = "Operating System Disk Size"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return f"{self.get_topic()}@size_in_mb"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect OS disk size(s) in MB.

        Returns:
            Dictionary with single key "operating_system_disk"
            Value is space-separated sizes in MB (e.g., "960197" or "960197 10000831")
        """
        # Get OS disk names using shared helper
        os_disk_names = self._get_os_disk_names(**kwargs)

        if not os_disk_names:
            return {"operating_system_disk": "0"}

        # Get all disk sizes using shared helper
        all_disk_sizes = self._get_all_disk_sizes(**kwargs)

        # Lookup sizes for OS disks
        os_disk_sizes = [str(all_disk_sizes.get(disk, "0")) for disk in os_disk_names]

        return {"operating_system_disk": self._get_separator().join(os_disk_sizes)}
