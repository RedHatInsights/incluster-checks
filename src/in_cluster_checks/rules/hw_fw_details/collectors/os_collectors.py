"""
OS/Kernel data collectors for Blueprint.

Collects operating system and kernel information from nodes following HealthChecks Blueprint pattern.
Based on HC flows/Blueprint/BlueprintDataCollectors.py OS/Kernel classes.
"""

from typing import Dict, List

from in_cluster_checks.rules.hw_fw_details.hw_fw_base import HwFwDataCollector
from in_cluster_checks.utils.enums import Objectives


class OSInfo(HwFwDataCollector):
    """Base class for OS/Kernel data collectors."""

    objective_hosts = [Objectives.ALL_NODES]

    def get_component_ids(self) -> List[str]:
        """
        Get OS component IDs.
        Follows HC pattern: single OS per system.

        Returns:
            List with single ID
        """
        return ["1"]


class OperatingSystemVersion(OSInfo):
    """
    Collect operating system version.
    Follows HC Blueprint pattern: Operating System@version
    """

    unique_name = "os_version"
    title = "Operating System Version"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Operating System@version"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect OS version.
        Follows HC OperatingSystemVersion.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {os_id: version}
            Example: {"1": "Red Hat Enterprise Linux 9.2"}
        """
        cmd = "cat /etc/redhat-release"
        os_version = self._run_cached_command(cmd, timeout=30).strip()

        return {os_id: os_version for os_id in self.get_component_ids()}


class KernelVersion(OSInfo):
    """
    Collect kernel version.
    Follows HC Blueprint pattern: Kernel@version
    """

    unique_name = "kernel_version"
    title = "Kernel Version"

    def get_objective_name(self) -> str:
        """Get blueprint objective name."""
        return "Kernel@version"

    def collect_data(self, **kwargs) -> Dict[str, str]:
        """
        Collect kernel version.
        Follows HC KernelVersion.collect_blueprint_data() pattern.

        Returns:
            Dictionary of {kernel_id: version}
            Example: {"1": "5.14.0-284.11.1.el9_2.x86_64"}
        """
        cmd = "uname -r"
        kernel_version = self._run_cached_command(cmd, timeout=30).strip()

        return {kernel_id: kernel_version for kernel_id in self.get_component_ids()}
