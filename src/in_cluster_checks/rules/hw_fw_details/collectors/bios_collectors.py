"""
BIOS data collectors for Blueprint.

Collects BIOS/firmware information from nodes following HealthChecks Blueprint pattern.
Based on HC flows/Blueprint/BlueprintDataCollectors.py BIOS classes.
"""

from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives


class BIOS(HwFwDataCollector):
    """Base class for BIOS data collectors."""

    objective_hosts = [Objectives.ALL_NODES]

    def get_component_ids(self) -> List[str]:
        """
        Get BIOS component IDs.
        Follows HC pattern: single BIOS per system.

        Returns:
            List with single ID
        """
        return ["1"]


class BIOSVersion(BIOS):
    """
    Collect BIOS version.
    Follows HC Blueprint pattern: Bios@version
    """

    unique_name = "bios_version"
    title = "BIOS Version"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Bios@version"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect BIOS version.
        Follows HC BIOSVersion.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {bios_id: version}
            Example: {"1": "2.8.0"}
        """
        cmd = "sudo dmidecode -s bios-version"
        bios_version = self._run_cached_command(cmd, timeout=30).strip()

        return {bios_id: bios_version for bios_id in self.get_component_ids()}


class BIOSFirmware(BIOS):
    """
    Collect BIOS firmware revision.
    Follows HC Blueprint pattern: Bios@firmware
    """

    unique_name = "bios_firmware"
    title = "BIOS Firmware"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Bios@firmware"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect BIOS firmware revision.

        Returns:
            Dictionary of {bios_id: firmware}
            Example: {"1": "1.68"}
        """
        cmd = "sudo dmidecode --type bios | grep 'Firmware Revision'"
        out = self._run_cached_command(cmd, timeout=30).strip()

        # Parse firmware from output (format: "Firmware Revision: 1.68")
        if ":" in out:
            bios_firmware = out.split(":", 1)[1].strip()
        else:
            bios_firmware = out if out else ""

        return {bios_id: bios_firmware for bios_id in self.get_component_ids()}


class BIOSRevision(BIOS):
    """
    Collect BIOS revision.
    Follows HC Blueprint pattern: Bios@revision
    """

    unique_name = "bios_revision"
    title = "BIOS Revision"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Bios@revision"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect BIOS revision.
        Follows HC BIOSRevision.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {bios_id: revision}
            Example: {"1": "2.50"}
        """
        cmd = "sudo dmidecode --type bios | grep -i 'BIOS Revision'"
        out = self._run_cached_command(cmd, timeout=30).strip()

        # Parse revision from output (format: "BIOS Revision: 2.50")
        if ":" in out:
            bios_revision = out.split(":", 1)[1].strip()
        else:
            bios_revision = out

        return {bios_id: bios_revision for bios_id in self.get_component_ids()}


class BIOSReleaseDate(BIOS):
    """
    Collect BIOS release date.
    Follows HC Blueprint pattern: Bios@release-date
    """

    unique_name = "bios_release_date"
    title = "BIOS Release Date"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Bios@release-date"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect BIOS release date.
        Follows HC BIOSReleaseDate.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {bios_id: release_date}
            Example: {"1": "12/15/2023"}
        """
        cmd = "sudo dmidecode -s bios-release-date"
        bios_release_date = self._run_cached_command(cmd, timeout=30).strip()

        return {bios_id: bios_release_date for bios_id in self.get_component_ids()}
