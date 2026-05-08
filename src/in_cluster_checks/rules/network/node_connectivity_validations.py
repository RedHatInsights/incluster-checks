"""
Node connectivity validations for OpenShift clusters.

Validates network connectivity across cluster nodes.
Ported from: support/HealthChecks/flows/Network/network_validations.py
"""

import os
import re

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, Rule, RuleResult
from in_cluster_checks.rules.network.ovs_base import OvsOperatorBase
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


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

    BONDING_PATH = "/proc/net/bonding"

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
        bond_list_out = self.get_output_from_run_cmd(
            SafeCmdString("ls {bonding_path}").format(bonding_path=self.BONDING_PATH)
        )
        bond_list = bond_list_out.strip().split()

        if not bond_list:
            return RuleResult.passed("No bonded interfaces found")

        failed_bonds = []

        for bond in bond_list:
            bond_file = os.path.join(self.BONDING_PATH, bond)

            # Get MII Status lines
            mii_out = self.get_output_from_run_cmd(
                SafeCmdString("cat {bond_file} | grep 'MII Status'").format(bond_file=bond_file)
            )
            mii_status_list = [line.split("MII Status: ")[1].strip() for line in mii_out.splitlines()]

            # Get Slave Interface lines
            slave_out = self.get_output_from_run_cmd(
                SafeCmdString("cat {bond_file} | grep 'Slave Interface'").format(bond_file=bond_file)
            )
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


class BondDnsCollector(OvsOperatorBase, DataCollector):
    """
    Collect DNS server information from all bond network interfaces.

    Discovers all bond interfaces dynamically and extracts IPv4 and IPv6
    DNS servers configured on each bond interface.
    Used by BondDnsServersComparison validator.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def _collect_dns_for_bonds(self, bond_devices: list[str]) -> dict:
        """
        Collect DNS server information for each bond interface.

        Args:
            bond_devices: List of bond device names (e.g., ['bond0', 'bond1'])

        Returns:
            Dictionary mapping bond interfaces to DNS configuration
            Example: {
                'bond0': {'ipv4': {'192.168.1.1'}, 'ipv6': set()},
                'bond1': {'ipv4': {'192.168.1.1'}, 'ipv6': set()}
            }
        """
        all_bonds_dns = {}
        for bond in bond_devices:
            cmd = SafeCmdString("nmcli conn show {bond}").format(bond=bond)
            out = self.get_output_from_run_cmd(cmd)

            # Extract DNS servers using regex
            ipv4_dns_servers = set(re.findall(r"ipv4\.dns:\s+([\d\.]+)", out))
            ipv6_dns_servers = set(re.findall(r"ipv6\.dns:\s+([\da-fA-F:]+)", out))

            all_bonds_dns[bond] = {"ipv4": ipv4_dns_servers, "ipv6": ipv6_dns_servers}

        return all_bonds_dns

    def collect_data(self, **kwargs) -> dict:
        """
        Collect DNS server data from all bond interfaces.

        Returns:
            Dictionary mapping bond interfaces to DNS configuration
            Example: {
                'bond0': {'ipv4': {'192.168.1.1'}, 'ipv6': set()},
                'bond1': {'ipv4': {'192.168.1.1'}, 'ipv6': set()}
            }
            Returns None if no bond connections exist
        """
        # Discover all bond interfaces
        connections = self._get_nmcli_connections(SafeCmdString("TYPE,DEVICE"), is_active=True)
        bond_devices = [conn["DEVICE"] for conn in connections if conn["TYPE"] == "bond" and conn["DEVICE"]]

        if not bond_devices:
            # No bond connections found (common on SNO or clusters without bonded interfaces)
            return None

        all_bonds_dns = self._collect_dns_for_bonds(bond_devices)

        return all_bonds_dns if all_bonds_dns else None


class BondDnsServersComparison(OrchestratorRule):
    """
    Compare bond DNS servers across all cluster nodes.

    Ensures all nodes have consistent DNS server configuration for all
    bond interfaces.
    Orchestrator validator - coordinates data collection across nodes.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "bond_dns_servers_comparison"
    title = "Compare bond DNS servers across hosts"
    links = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Network-%E2%80%90-Bond-DNS-Servers-Comparison",
    ]

    def run_rule(self):
        """
        Run rule check.

        Collects DNS data from all nodes and compares for consistency.

        Returns:
            RuleResult with status and optional message
        """
        # Collect DNS data from all nodes
        dns_servers = self.run_data_collector(BondDnsCollector)

        # Check if collection failed on any nodes
        exceptions = self.get_data_collector_exceptions(BondDnsCollector)
        if exceptions:
            failed_nodes = ", ".join(sorted(exceptions.keys()))
            return RuleResult.failed(
                f"Failed to collect DNS data from {len(exceptions)} node(s): {failed_nodes}. "
                f"Cannot reliably compare DNS configuration with incomplete data."
            )

        # Compare DNS across nodes
        return self._compare_dns_across_hosts(dns_servers)

    def _find_dns_mismatches_for_bond(self, nodes_with_bond: dict) -> tuple[list, list]:
        """
        Find DNS mismatches for a single bond interface across nodes.

        Args:
            nodes_with_bond: Dict of {hostname: {'ipv4': set, 'ipv6': set}}

        Returns:
            Tuple of (ipv4_mismatches, ipv6_mismatches)
            Each mismatch is a dict with 'host' and 'dns_server' keys
        """
        reference_host = next(iter(nodes_with_bond))
        reference_dns = nodes_with_bond[reference_host]

        ipv4_mismatch = []
        ipv6_mismatch = []

        for host, dns in nodes_with_bond.items():
            if dns["ipv4"] != reference_dns["ipv4"]:
                ipv4_mismatch.append({"host": host, "dns_server": dns["ipv4"]})

            if dns["ipv6"] != reference_dns["ipv6"]:
                ipv6_mismatch.append({"host": host, "dns_server": dns["ipv6"]})

        return ipv4_mismatch, ipv6_mismatch

    def _build_mismatch_message(
        self, bond_name: str, reference_host: str, reference_dns: dict, ipv4_mismatch: list, ipv6_mismatch: list
    ) -> str:
        """
        Build formatted mismatch message for a bond interface.

        Args:
            bond_name: Name of the bond interface
            reference_host: Hostname used as reference
            reference_dns: Reference DNS config {'ipv4': set, 'ipv6': set}
            ipv4_mismatch: List of IPv4 mismatches
            ipv6_mismatch: List of IPv6 mismatches

        Returns:
            Formatted multi-line string describing the mismatches
        """
        bond_mismatch = [f"Bond interface: {bond_name}"]

        if ipv4_mismatch:
            bond_mismatch.append(f"  IPv4 DNS mismatch (reference: {reference_host} = {list(reference_dns['ipv4'])}):")
            for mismatch in ipv4_mismatch:
                if mismatch["host"] != reference_host:
                    bond_mismatch.append(f"    {mismatch['host']}: {list(mismatch['dns_server'])}")

        if ipv6_mismatch:
            bond_mismatch.append(f"  IPv6 DNS mismatch (reference: {reference_host} = {list(reference_dns['ipv6'])}):")
            for mismatch in ipv6_mismatch:
                if mismatch["host"] != reference_host:
                    bond_mismatch.append(f"    {mismatch['host']}: {list(mismatch['dns_server'])}")

        return "\n".join(bond_mismatch)

    def _compare_dns_across_hosts(self, dns_servers: dict):
        """
        Compare DNS servers across all hosts for all bond interfaces.

        Args:
            dns_servers: Dictionary of {hostname: {bond_name: {'ipv4': set, 'ipv6': set}} or None}

        Returns:
            RuleResult with status and optional message
        """
        valid_dns_servers = {host: dns for host, dns in dns_servers.items() if dns is not None}

        if not valid_dns_servers:
            return RuleResult.not_applicable("No bond interfaces found on any node")

        all_bond_names = set()
        for host_bonds in valid_dns_servers.values():
            all_bond_names.update(host_bonds.keys())

        all_mismatches = []

        for bond_name in sorted(all_bond_names):
            nodes_with_bond = {
                host: bonds[bond_name] for host, bonds in valid_dns_servers.items() if bond_name in bonds
            }

            if not nodes_with_bond:
                continue

            ipv4_mismatch, ipv6_mismatch = self._find_dns_mismatches_for_bond(nodes_with_bond)

            if ipv4_mismatch or ipv6_mismatch:
                reference_host = next(iter(nodes_with_bond))
                reference_dns = nodes_with_bond[reference_host]
                mismatch_msg = self._build_mismatch_message(
                    bond_name, reference_host, reference_dns, ipv4_mismatch, ipv6_mismatch
                )
                all_mismatches.append(mismatch_msg)

        if all_mismatches:
            message = "DNS server mismatch found across nodes:\n\n" + "\n\n".join(all_mismatches)
            return RuleResult.failed(message)

        return RuleResult.passed(
            f"DNS configuration consistent across all nodes for {len(all_bond_names)} bond interfaces"
        )


class VerifyDnsReachability(Rule):
    """
    Verify DNS reachability in the cluster.

    This rule checks if DNS servers are reachable by:
    1. Checking if the cluster DNS operator is healthy
    2. Finding DNS server IPs from /etc/resolv.conf
    3. Pinging each DNS server to verify reachability

    Note: This checks DNS server reachability, NOT domain name resolution.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "verify_dns_reachability"
    title = "Verify DNS reachability"
    links = ["https://github.com/RedHatInsights/incluster-checks/wiki/Network-‐-Verify-DNS-reachability"]

    DNS_OPERATOR = "dns"
    RESOLV_CONF_PATH = "/etc/resolv.conf"

    def run_rule(self) -> RuleResult:
        """
        Verify DNS reachability.

        Returns:
            RuleResult indicating DNS health and reachability status
        """
        # Step 1: Check DNS operator health
        is_healthy, operator_msg = self._check_dns_operator_health()
        if not is_healthy:
            return RuleResult.failed(f"DNS operator health check failed: {operator_msg}")

        # Step 2: Find DNS servers from /etc/resolv.conf
        dns_servers = self._get_dns_servers_from_resolv_conf()
        if not dns_servers:
            return RuleResult.failed("No DNS servers found in /etc/resolv.conf")

        # Step 3: Ping each DNS server
        unreachable_servers = []
        for dns_server in dns_servers:
            if not self._ping_dns_server(dns_server):
                unreachable_servers.append(dns_server)

        if unreachable_servers:
            return RuleResult.failed(
                f"DNS servers unreachable: {', '.join(unreachable_servers)}\n({operator_msg})"
            )

        return RuleResult.passed(
            f"All DNS servers are reachable ({len(dns_servers)} servers checked): {', '.join(dns_servers)}"
        )

    def _check_dns_operator_health(self) -> tuple[bool, str]:
        """
        Check if the DNS operator is healthy.

        Returns:
            Tuple of (is_healthy, message)
        """
        try:
            _, operator_output, _ = self.oc_api.run_oc_command(
                "get", ["clusteroperator", self.DNS_OPERATOR, "--no-headers"], timeout=30
            )
        except UnExpectedSystemOutput as e:
            return False, f"Failed to get DNS operator status: {e}"

        if not operator_output or not operator_output.strip():
            return False, f"DNS operator '{self.DNS_OPERATOR}' not found"

        operator_values = operator_output.strip().split()

        if len(operator_values) < 5:
            return False, f"Unexpected DNS operator output format: {operator_output}"

        name = operator_values[0]
        available = operator_values[2]
        progressing = operator_values[3]
        degraded = operator_values[4]

        issues = []
        if available != "True":
            issues.append(f"not available (Available={available})")
        if progressing == "True":
            issues.append(f"in progress (Progressing={progressing})")
        if degraded == "True":
            issues.append(f"degraded (Degraded={degraded})")

        if issues:
            return False, f"DNS operator '{name}' is {', '.join(issues)}"

        return True, f"DNS operator '{name}' is healthy"

    def _get_dns_servers_from_resolv_conf(self) -> list[str]:
        """
        Extract DNS server IPs from /etc/resolv.conf.

        Returns:
            List of DNS server IP addresses
        """
        cmd = SafeCmdString("cat {resolv_conf} | grep '^nameserver'").format(resolv_conf=self.RESOLV_CONF_PATH)
        output = self.get_output_from_run_cmd(cmd)

        dns_servers = []
        for line in output.splitlines():
            # Each line format: "nameserver <IP>"
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == "nameserver":
                dns_servers.append(parts[1])

        return dns_servers

    def _ping_dns_server(self, dns_server: str) -> bool:
        """
        Ping a DNS server to check if it's reachable.

        Args:
            dns_server: DNS server IP address

        Returns:
            True if DNS server is reachable, False otherwise
        """
        cmd = SafeCmdString("ping -c 1 -W 2 {dns_server}").format(dns_server=dns_server)
        rc, _, _ = self.run_cmd(cmd)
        return rc == 0
