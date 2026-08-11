"""
NIC (Network Interface Card) data collectors for Blueprint hardware validation.

Collects network interface information (vendor, model, speed) from lshw and ethtool.
Based on HealthChecks NICBlueprintDataCollectors pattern.
"""

import re
from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class NICDataCollector(HwFwDataCollector):
    """
    Base class for NIC data collectors.

    Provides shared logic for getting NIC IDs and port information.
    All NIC collectors inherit from this class.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def get_component_ids(self) -> List[str]:
        """
        Get NIC IDs from lspci.

        Returns:
            List of NIC IDs (e.g., ["01:00.0", "02:00.0"])
            Each NIC ID represents the first port (.0) of each physical NIC
        """
        nic_ports_dict = self._get_nic_ports_ids_dict()
        return sorted(nic_ports_dict.keys())

    def _get_nic_ports_ids_dict(self) -> Dict[str, List[str]]:
        """
        Get dictionary of NIC IDs to their port IDs.

        Returns:
            Dict of {nic_id: [port_id1, port_id2, ...]}
            Example: {"01:00": ["01:00.0", "01:00.1"]}
        """
        cmd = SafeCmdString("sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'")
        output = self._run_cached_command(cmd, timeout=30)

        nic_ports_ids = {}
        for line in output.splitlines():
            if line.strip():
                # Extract PCI ID (first field)
                port_id = line.split()[0]
                # Get NIC ID (strip port number)
                nic_id = port_id.split(".")[0]

                # Add port to NIC's port list
                if nic_id not in nic_ports_ids:
                    nic_ports_ids[nic_id] = []
                nic_ports_ids[nic_id].append(port_id)

        return nic_ports_ids

    def _get_nic_ports_names_dict(self) -> Dict[str, List[str]]:
        """
        Get dictionary of NIC IDs to their logical port names.

        Uses /sys/class/net to map PCI addresses to interface names.
        Alternative to lshw which is not available on all systems.

        Returns:
            Dict of {nic_id: [port_name1, port_name2, ...]}
            Example: {"01:00": ["eth0", "eth1"]}
        """
        nic_ports_ids = self._get_nic_ports_ids_dict()

        nic_ports_names = {}
        for nic_id, port_ids in nic_ports_ids.items():
            nic_ports_names[nic_id] = []
            for port_id in port_ids:
                port_name = self._get_port_name_from_sysfs(port_id)
                if port_name and port_name != "----":
                    nic_ports_names[nic_id].append(port_name)

        return nic_ports_names

    def _get_port_name_from_sysfs(self, port_id: str) -> str:
        """
        Get logical port name for specific PCI port ID using /sys/class/net.

        Args:
            port_id: PCI ID like "12:00.0"

        Returns:
            Logical interface name like "ens1f0np0" or "----" if not found
        """
        # Get all physical interfaces by listing directories with device symlink
        # Use ls -d to list directories, not their contents
        cmd = SafeCmdString("ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5")
        output = self._run_cached_command(cmd, timeout=30)

        # Check each physical interface
        for iface in output.strip().split():
            if not iface:
                continue

            # Get PCI address via readlink
            pci_cmd = SafeCmdString("readlink /sys/class/net/{iface}/device 2>/dev/null").format(iface=iface)
            pci_output = self._run_cached_command(pci_cmd, timeout=30).strip()

            # readlink returns something like "../../../0000:12:00.0"
            # Extract just the PCI ID part
            if ":" in pci_output:
                # Get the last component (PCI ID with full domain)
                pci_addr = pci_output.split("/")[-1]

                # Normalize both addresses for comparison
                # lspci may output with or without domain prefix depending on system
                # readlink always includes domain
                # Normalize port_id: if it doesn't have domain (e.g., "12:00.0"), prepend "0000:"
                normalized_port_id = port_id if port_id.count(":") >= 2 else f"0000:{port_id}"

                # Match against normalized port_id
                if pci_addr == normalized_port_id:
                    return iface

        return "----"

    def _get_nics_values_dict(self, field: str) -> Dict[str, str]:
        """
        Get field value from lspci for each NIC (using first port).

        Uses lspci -vmm which provides easy-to-parse output.
        Alternative to lshw which is not available on all systems.

        Args:
            field: Field name from lspci -vmm (e.g., "Vendor", "Device")

        Returns:
            Dict of {nic_id: field_value}
        """
        nic_ports_ids = self._get_nic_ports_ids_dict()

        result = {}
        for nic_id, port_ids in nic_ports_ids.items():
            # Use first port to get NIC info
            first_port = port_ids[0]

            # Get detailed info for this PCI device
            cmd = SafeCmdString("sudo lspci -vmm -s {first_port}").format(first_port=first_port)
            output = self._run_cached_command(cmd, timeout=30)

            # Parse lspci -vmm output (key-value pairs)
            value = self._parse_lspci_vmm(output, field)
            result[nic_id] = value if value else "----"

        return result

    def _parse_lspci_vmm(self, output: str, field: str) -> str:
        """
        Parse lspci -vmm output to extract specific field.

        Args:
            output: Output from lspci -vmm command
            field: Field name to extract (e.g., "Vendor", "Device")

        Returns:
            Field value or empty string if not found
        """
        for line in output.splitlines():
            if line.startswith(f"{field}:"):
                value = line.split(":", 1)[1].strip()
                return value if value else ""
        return ""

    def get_objective_name(self) -> str:
        """Get blueprint objective name - override in subclass."""
        return "Network Interface@unknown"


class NICVendor(NICDataCollector):
    """
    Collect NIC vendor information.

    Uses lshw to get vendor for each network interface.
    Follows HC Blueprint pattern: Network Interface@vendor
    """

    unique_name = "nic_vendor"
    title = "NIC Vendor"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@vendor"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect NIC vendor for each network interface.

        Returns:
            Dictionary of {nic_id: vendor}
            Example: {"01:00": "Intel Corporation", "02:00": "Broadcom Inc."}
        """
        return self._get_nics_values_dict("Vendor")


class NICModel(NICDataCollector):
    """
    Collect NIC model information.

    Uses lshw to get product/model for each network interface.
    Follows HC Blueprint pattern: Network Interface@model
    """

    unique_name = "nic_model"
    title = "NIC Model"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@model"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect NIC model for each network interface.

        Returns:
            Dictionary of {nic_id: model}
            Example: {"01:00": "82599ES 10-Gigabit", "02:00": "NetXtreme BCM5720"}
        """
        return self._get_nics_values_dict("Device")


class NICSpeed(NICDataCollector):
    """
    Collect NIC maximum speed.

    Uses ethtool to get maximum supported speed for each network interface.
    Follows HC Blueprint pattern: Network Interface@speed_in_mb
    """

    unique_name = "nic_speed"
    title = "NIC Speed"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@speed_in_mb"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect NIC maximum speed for each network interface.

        Uses first port of each NIC to determine max speed.
        All ports on same NIC should have same max speed.

        Returns:
            Dictionary of {nic_id: speed_in_mb}
            Example: {"01:00": 10000, "02:00": 1000}
        """
        nic_ports_names = self._get_nic_ports_names_dict()

        result = {}
        for nic_id, port_names in nic_ports_names.items():
            if port_names:
                # Use first port to get speed
                speed = self._get_speed_from_port(port_names[0])
                result[nic_id] = speed
            else:
                result[nic_id] = 0

        return result

    def _get_speed_from_port(self, port_name: str) -> int:
        """
        Get maximum speed for port using ethtool.

        Returns speed in Mb/s (e.g., 1000, 10000, 25000)
        """
        cmd = SafeCmdString("sudo ethtool {port_name}").format(port_name=port_name)
        output = self._run_cached_command(cmd, timeout=30)

        # Look for "Supported link modes:" section
        # Extract text between "Supported link modes:" and next section
        supported_match = re.search(
            r"Supported link modes:(.+?)(?:Supported pause|Supported auto-negotiation|Speed:|\n\S)", output, re.DOTALL
        )

        if not supported_match:
            return 0

        supported_speeds_text = supported_match.group(1)

        # Extract all speed numbers (e.g., "1000baseT/Full" -> 1000)
        speed_numbers = re.findall(r"(\d+)base", supported_speeds_text)

        if not speed_numbers:
            return 0

        # Return maximum supported speed
        return max([int(speed) for speed in speed_numbers])


class NICPortsAmount(NICDataCollector):
    """
    Collect number of ports for each NIC.

    Uses lspci to count physical ports per network interface.
    Follows HC Blueprint pattern: Network Interface@ports_amount
    """

    unique_name = "nic_ports_amount"
    title = "NIC Ports Amount"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@ports_amount"

    def collect_data(self, **kwargs) -> Dict[str, int]:
        """
        Collect number of ports for each NIC.

        Returns:
            Dictionary of {nic_id: ports_count}
            Example: {"12:00": 2, "9f:00": 2}
        """
        nic_ports_ids = self._get_nic_ports_ids_dict()

        result = {}
        for nic_id, port_ids in nic_ports_ids.items():
            result[nic_id] = len(port_ids)

        return result


class NICPortsNames(NICDataCollector):
    """
    Collect logical port names for each NIC.

    Uses lshw to map PCI IDs to logical interface names.
    Follows HC Blueprint pattern: Network Interface@ports_names
    """

    unique_name = "nic_ports_names"
    title = "NIC Ports Names"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@ports_names"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect logical port names for each NIC.

        Returns:
            Dictionary of {nic_id: "port1 port2 ..."}
            Example: {"12:00": "ens1f0np0 ens1f1np1"}
        """
        nic_ports_names = self._get_nic_ports_names_dict()

        result = {}
        for nic_id, port_names in nic_ports_names.items():
            # Join port names with space
            result[nic_id] = " ".join(port_names) if port_names else "----"

        return result


class NICVersion(NICDataCollector):
    """
    Collect NIC driver version.

    Uses ethtool -i to get driver version for each network interface.
    Follows HC Blueprint pattern: Network Interface@version
    """

    unique_name = "nic_version"
    title = "NIC Version"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@version"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect NIC driver version for each network interface.

        Uses first port of each NIC since all ports share same driver version.

        Returns:
            Dictionary of {nic_id: version}
            Example: {"12:00": "5.14.0-570.83.1.el9_6.x86_64"}
        """
        return self._get_nics_ethtool_field("version")

    def _get_nics_ethtool_field(self, field: str) -> Dict[str, str]:
        """
        Get field value from ethtool -i for each NIC.

        Args:
            field: Field name (driver, version, firmware-version)

        Returns:
            Dict of {nic_id: field_value}
        """
        nic_ports_names = self._get_nic_ports_names_dict()

        result = {}
        for nic_id, port_names in nic_ports_names.items():
            if not port_names:
                result[nic_id] = "----"
                continue

            # Use first port (all ports on same NIC have same values)
            first_port = port_names[0]
            cmd = SafeCmdString("sudo ethtool -i {first_port}").format(first_port=first_port)
            output = self._run_cached_command(cmd, timeout=30)

            # Parse ethtool -i output for the field
            field_value = self._parse_ethtool_field(output, field)
            result[nic_id] = field_value

        return result

    def _parse_ethtool_field(self, output: str, field: str) -> str:
        """Parse ethtool -i output to extract specific field."""
        for line in output.splitlines():
            if line.startswith(f"{field}:"):
                value = line.split(":", 1)[1].strip()
                return value if value else "----"
        return "----"


class NICFirmware(NICDataCollector):
    """
    Collect NIC firmware version.

    Uses ethtool -i to get firmware version for each network interface.
    Follows HC Blueprint pattern: Network Interface@firmware
    """

    unique_name = "nic_firmware"
    title = "NIC Firmware"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@firmware"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect NIC firmware version for each network interface.

        Uses first port of each NIC since all ports share same firmware.

        Returns:
            Dictionary of {nic_id: firmware_version}
            Example: {"12:00": "26.44.1036 (MT_0000000575)"}
        """
        nic_ports_names = self._get_nic_ports_names_dict()

        result = {}
        for nic_id, port_names in nic_ports_names.items():
            if not port_names:
                result[nic_id] = "----"
                continue

            first_port = port_names[0]
            cmd = SafeCmdString("sudo ethtool -i {first_port}").format(first_port=first_port)
            output = self._run_cached_command(cmd, timeout=30)

            # Parse for firmware-version field
            firmware = self._parse_ethtool_field(output, "firmware-version")
            result[nic_id] = firmware

        return result

    def _parse_ethtool_field(self, output: str, field: str) -> str:
        """Parse ethtool -i output to extract specific field."""
        for line in output.splitlines():
            if line.startswith(f"{field}:"):
                value = line.split(":", 1)[1].strip()
                return value if value else "----"
        return "----"


class NICDriver(NICDataCollector):
    """
    Collect NIC driver name.

    Uses ethtool -i to get driver name for each network interface.
    Follows HC Blueprint pattern: Network Interface@driver
    """

    unique_name = "nic_driver"
    title = "NIC Driver"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Network Interface@driver"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect NIC driver name for each network interface.

        Uses first port of each NIC since all ports share same driver.

        Returns:
            Dictionary of {nic_id: driver_name}
            Example: {"12:00": "mlx5_core"}
        """
        nic_ports_names = self._get_nic_ports_names_dict()

        result = {}
        for nic_id, port_names in nic_ports_names.items():
            if not port_names:
                result[nic_id] = "----"
                continue

            first_port = port_names[0]
            cmd = SafeCmdString("sudo ethtool -i {first_port}").format(first_port=first_port)
            output = self._run_cached_command(cmd, timeout=30)

            # Parse for driver field
            driver = self._parse_ethtool_field(output, "driver")
            result[nic_id] = driver

        return result

    def _parse_ethtool_field(self, output: str, field: str) -> str:
        """Parse ethtool -i output to extract specific field."""
        for line in output.splitlines():
            if line.startswith(f"{field}:"):
                value = line.split(":", 1)[1].strip()
                return value if value else "----"
        return "----"
