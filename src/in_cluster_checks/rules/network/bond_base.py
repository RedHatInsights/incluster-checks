"""
Base class for network bond validation rules.

Provides common functionality for rules that validate bonded network interfaces.
"""

from in_cluster_checks.core.rule import PrerequisiteResult, Rule


class BondBase(Rule):
    """
    Base class for bond-related validation rules.

    Provides common prerequisite checking for rules that require
    bond interfaces to be configured on the node.
    """

    BONDING_PATH = "/proc/net/bonding"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if bond interfaces exist on this node.

        Returns:
            PrerequisiteResult indicating if bonding is configured
        """
        if self.file_utils.is_dir_exist(self.BONDING_PATH):
            return PrerequisiteResult.met()
        return PrerequisiteResult.not_met("No bond interfaces configured")
