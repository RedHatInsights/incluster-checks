"""
Node connectivity validations for OpenShift clusters.

Validates network connectivity across cluster nodes.
Ported from: support/HealthChecks/flows/Network/network_validations.py
"""

import os

from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, Rule, RuleResult
from in_cluster_checks.utils.enums import Objectives


class AreAllNodesConnected(OrchestratorRule):
    """
    Verify that all nodes in the system are connected.

    Checks if all node executors can successfully communicate with their nodes.
    Orchestrator-level validator that checks connectivity across all nodes.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "are_all_nodes_connected"
    title = "Verify that all nodes in the system are connected"

    def run_rule(self) -> RuleResult:
        """
        Check if all nodes are connected.

        Returns:
            RuleResult indicating if all nodes are connected
        """
        if not self._node_executors:
            return RuleResult.skip("No node executors available")

        not_connected = []
        for node_name, executor in self._node_executors.items():
            # Check if executor has is_connected attribute and if it's False
            is_connected = getattr(executor, "is_connected", True)
            if not is_connected:
                not_connected.append(node_name)

        if not_connected:
            message = f"Following nodes are not connected:\n{chr(10).join(not_connected)}"
            return RuleResult.failed(message)

        return RuleResult.passed(f"All {len(self._node_executors)} nodes are connected")


class VerifyBondedInterfacesUp(Rule):
    """
    Check if bonded network interfaces are up.

    Validates that all bonded interfaces in /proc/net/bonding/ have their
    MII Status as 'up'. Identifies any down interfaces that could cause
    network connectivity issues.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "check_if_bonded_interfaces_are_up"
    title = "Check if bonded interfaces are up"

    BONDING_PATH = "/proc/net/bonding/"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if bonding directory exists.

        Returns:
            PrerequisiteResult indicating if bonding is configured
        """
        if self.file_utils.is_dir_exist(self.BONDING_PATH):
            return PrerequisiteResult.met()
        return PrerequisiteResult.not_met("Bonding directory does not exist - no bonded interfaces configured")

    def run_rule(self) -> RuleResult:
        """
        Verify all bonded interfaces are up.

        Returns:
            RuleResult indicating status of bonded interfaces
        """
        # Get list of bond interfaces
        bond_list_out = self.get_output_from_run_cmd(f"ls {self.BONDING_PATH}")
        bond_list = bond_list_out.strip().split()

        if not bond_list:
            return RuleResult.passed("No bonded interfaces found")

        failed_bonds = []

        for bond in bond_list:
            bond_file = os.path.join(self.BONDING_PATH, bond)

            # Get MII Status lines
            mii_out = self.get_output_from_run_cmd(f"cat {bond_file} | grep 'MII Status'")
            mii_status_list = [line.split("MII Status: ")[1].strip() for line in mii_out.splitlines()]

            # Get Slave Interface lines
            slave_out = self.get_output_from_run_cmd(f"cat {bond_file} | grep 'Slave Interface'")
            interfaces_list = [line.split("Slave Interface: ")[1].strip() for line in slave_out.splitlines()]
            interfaces_list.insert(0, "master")

            # Find down interfaces
            down_indexes = [i for i in range(len(mii_status_list)) if mii_status_list[i] == "down"]

            if down_indexes:
                down_interfaces = [interfaces_list[i] for i in down_indexes]
                failed_bonds.append(f"{bond}: some bonded interfaces are down: {down_interfaces}")

        if failed_bonds:
            message = "\n".join(failed_bonds)
            return RuleResult.failed(message)

        return RuleResult.passed(f"All bonded interfaces are up ({len(bond_list)} bonds checked)")
