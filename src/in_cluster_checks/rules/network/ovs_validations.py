"""
OVS (Open vSwitch) network validations.

Ported from support/HealthChecks/flows/Network/ovs_validations.py
"""

import re

from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives


class OvsInterfaceAndPortFound(Rule):
    """
    Verify that OVS interface and port are managed by NetworkManager.

    Checks for presence of:
    - ovs-if-phys (OVS interface)
    - ovs-port-phys (OVS port)

    These should be present in nmcli connection show output on nodes.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "ovs_interface_and_port_managed_by_network_manager"
    title = "Verify that ovs interface and port are managed by network manager"

    def run_rule(self):
        """
        Run rule check.

        Returns:
            RuleResult indicating if both ovs-if-phys and ovs-port-phys exist
        """
        # Get NetworkManager connections
        connections = self.get_output_from_run_cmd("nmcli connection show").splitlines()

        # Check for ovs-if-phys and ovs-port-phys
        is_interface_exist = any(line.startswith("ovs-if-phys") for line in connections)
        is_port_exist = any(line.startswith("ovs-port-phys") for line in connections)

        # Build failure message if either is missing
        missing_items = []
        if not is_interface_exist:
            missing_items.append("ovs-if-phys doesn't exist in network manager connections")

        if not is_port_exist:
            missing_items.append("ovs-port-phys doesn't exist in network manager connections")

        if missing_items:
            return RuleResult.failed(".\n".join(missing_items) + ".")

        return RuleResult.passed()


class Bond0Dns(DataCollector):
    """
    Collect DNS server information from bond0 network interface.

    Extracts IPv4 and IPv6 DNS servers configured on bond0.
    Used by Bond0DnsServersComparison validator.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def collect_data(self, **kwargs) -> dict:
        """
        Collect DNS server data from bond0.

        Returns:
            Dictionary with 'ipv4' and 'ipv6' DNS server sets
            Example: {'ipv4': {'8.8.8.8', '8.8.4.4'}, 'ipv6': set()}
            Returns None if bond0 connection doesn't exist
        """
        cmd = "nmcli conn show bond0"

        # Try to get bond0 connection info
        # If bond0 doesn't exist, return None (not an error, just doesn't apply)
        rc, out, err = self.run_cmd(cmd)

        if rc != 0:
            # bond0 connection doesn't exist (common on SNO or clusters without bonded interfaces)
            self.add_to_rule_log(f"bond0 connection not found: {err.strip()}")
            return None

        # Extract DNS servers using regex
        ipv4_dns_servers = set(re.findall(r"ipv4\.dns:\s+([\d\.]+)", out))
        ipv6_dns_servers = set(re.findall(r"ipv6\.dns:\s+([\da-fA-F:]+)", out))

        dns_servers = {"ipv4": ipv4_dns_servers, "ipv6": ipv6_dns_servers}

        return dns_servers


class Bond0DnsServersComparison(OrchestratorRule):
    """
    Compare bond0 DNS servers across all cluster nodes.

    Ensures all nodes have consistent DNS server configuration.
    Orchestrator validator - coordinates data collection across nodes.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "bond0_dns_servers_comparison"
    title = "Compare bond0 DNS servers across hosts"

    def run_rule(self):
        """
        Run rule check.

        Collects DNS data from all nodes and compares for consistency.

        Returns:
            RuleResult with status and optional message
        """
        # Collect DNS data from all nodes
        dns_servers = self.run_data_collector(Bond0Dns)

        # Compare DNS across nodes
        return self._compare_dns_across_hosts(dns_servers)

    def _compare_dns_across_hosts(self, dns_servers: dict):
        """
        Compare DNS servers across all hosts.

        Args:
            dns_servers: Dictionary of {hostname: {'ipv4': set, 'ipv6': set} or None}

        Returns:
            RuleResult with status and optional message
        """
        # Filter out None values (hosts without bond0)
        valid_dns_servers = {host: dns for host, dns in dns_servers.items() if dns is not None}

        # If no hosts have bond0, validation passes (not applicable)
        if not valid_dns_servers:
            self.add_to_rule_log("bond0 interface not found on any node - validation not applicable")
            return RuleResult.passed("bond0 interface not found on any node - validation not applicable")

        # If some nodes have bond0 and others don't, that's a failure
        if len(valid_dns_servers) != len(dns_servers):
            missing_bond0_hosts = [host for host, dns in dns_servers.items() if dns is None]
            message = f"bond0 interface missing on some nodes: {', '.join(missing_bond0_hosts)}"
            return RuleResult.failed(message)

        # Use first host as reference
        reference_host = next(iter(valid_dns_servers))
        reference_dns = valid_dns_servers[reference_host]

        ipv4_mismatch = []
        ipv6_mismatch = []

        # Compare each host against reference
        for host, dns in valid_dns_servers.items():
            if dns["ipv4"] != reference_dns["ipv4"]:
                ipv4_mismatch.append({"host": host, "dns_server": dns["ipv4"]})

            if dns["ipv6"] != reference_dns["ipv6"]:
                ipv6_mismatch.append({"host": host, "dns_server": dns["ipv6"]})

        # Build failure message if mismatches found
        if ipv4_mismatch or ipv6_mismatch:
            message_parts = ["Mismatch in DNS server was found on:"]

            if ipv4_mismatch:
                message_parts.append(
                    f"IPV4 DNS server isn't equal to host: {reference_host}, server: {list(reference_dns['ipv4'])}:"
                )
                for mismatch in ipv4_mismatch:
                    message_parts.append(f"host: {mismatch['host']} server: {list(mismatch['dns_server'])}")

            if ipv6_mismatch:
                message_parts.append(
                    f"IPV6 DNS server isn't equal to host: {reference_host}, server: {list(reference_dns['ipv6'])}:"
                )
                for mismatch in ipv6_mismatch:
                    message_parts.append(f"host: {mismatch['host']} server: {list(mismatch['dns_server'])}")

            return RuleResult.failed("\n".join(message_parts))

        return RuleResult.passed()
