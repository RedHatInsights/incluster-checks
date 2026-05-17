"""
DNS reachability validations for OpenShift clusters.

Validates DNS server reachability by checking upstream DNS resolvers
and testing connectivity via ping.
"""

import json

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DnsReachabilityCollector(DataCollector):
    """
    Test DNS server reachability from each node.

    Tests reachability of DNS servers (either from upstream config or /etc/resolv.conf)
    by pinging each server from the node.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def collect_data(self, **kwargs) -> dict:
        """
        Test DNS server reachability.

        Args:
            **kwargs: Optional 'upstream_dns_servers' list to test specific servers.
                     If not provided, reads from /etc/resolv.conf.

        Returns:
            Dictionary with reachability results, or None if no DNS servers found
            Example: {
                'source': 'upstream resolvers',
                'reachable': ['192.168.1.1'],
                'unreachable': ['8.8.8.8']
            }
        """
        # Get DNS servers to test (from upstream config or /etc/resolv.conf)
        upstream_dns_servers = kwargs.get("upstream_dns_servers")

        if upstream_dns_servers:
            dns_servers = upstream_dns_servers
            source = "cluster upstream resolvers"
        else:
            # Read from /etc/resolv.conf
            dns_servers = self._get_nameservers_from_resolv_conf()
            source = "/etc/resolv.conf"

        if not dns_servers:
            return None

        # Ping each DNS server
        reachable = []
        unreachable = []

        for dns_ip in dns_servers:
            # Determine if IPv6 or IPv4
            is_ipv6 = ":" in dns_ip

            # Ping the DNS server (3 packets, 2 second timeout)
            if is_ipv6:
                ping_cmd = SafeCmdString("ping -6 -c 3 -W 2 {ip}").format(ip=dns_ip)
            else:
                ping_cmd = SafeCmdString("ping -c 3 -W 2 {ip}").format(ip=dns_ip)

            return_code, _, _ = self.run_cmd(ping_cmd)

            if return_code == 0:
                reachable.append(dns_ip)
            else:
                unreachable.append(dns_ip)

        return {"source": source, "reachable": reachable, "unreachable": unreachable}

    def _get_nameservers_from_resolv_conf(self) -> list[str]:
        """
        Extract nameserver entries from /etc/resolv.conf.

        Returns:
            List of DNS server IP addresses
        """
        resolv_conf_path = "/etc/resolv.conf"

        # Check if file exists
        if not self.file_utils.is_file_exist(resolv_conf_path):
            return []

        # Read resolv.conf
        resolv_conf_content = self.get_output_from_run_cmd(SafeCmdString("cat {path}").format(path=resolv_conf_path))

        # Extract nameserver entries
        nameservers = []
        for line in resolv_conf_content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if line.startswith("#") or not line:
                continue
            # Match nameserver lines
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    nameserver_ip = parts[1]
                    nameservers.append(nameserver_ip)

        return nameservers


class VerifyDnsReachability(OrchestratorRule):
    """
    Verify DNS server reachability.

    This validation checks:
    1. Looks for upstream DNS resolvers in the cluster DNS operator config
    2. If found, tests those DNS servers from each node
    3. If not configured, checks /etc/resolv.conf on each node and tests those DNS servers
    4. Reports which DNS servers are reachable/unreachable

    Orchestrator-level validator that coordinates DNS checks across the cluster.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_dns_reachability"
    title = "Verify DNS server reachability"
    links = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Network-%E2%80%90-Verify-DNS-reachability",
    ]

    def run_rule(self) -> RuleResult:
        """
        Check DNS server reachability.

        Returns:
            RuleResult indicating DNS reachability status
        """
        # Step 1: Try to get upstream DNS resolvers from cluster config
        upstream_dns_servers = self._get_upstream_dns_resolvers()

        # Step 2: Run DNS reachability tests on nodes
        if upstream_dns_servers:
            # Test upstream DNS servers from all nodes
            reachability_data = self.run_data_collector(
                DnsReachabilityCollector, upstream_dns_servers=upstream_dns_servers
            )
        else:
            # No upstream resolvers - let each node test its own /etc/resolv.conf
            reachability_data = self.run_data_collector(DnsReachabilityCollector)

        # Check for collection failures
        exceptions = self.get_data_collector_exceptions(DnsReachabilityCollector)
        if exceptions:
            failed_nodes = ", ".join(sorted(exceptions.keys()))
            return RuleResult.failed(
                f"Failed to test DNS reachability from {len(exceptions)} node(s): {failed_nodes}. "
                f"Cannot verify DNS reachability with incomplete data."
            )

        # Check if any data was collected
        if not reachability_data:
            return RuleResult.failed(
                "No DNS servers found. "
                "Neither upstream DNS resolvers configured nor nameservers in /etc/resolv.conf."
            )

        # Aggregate results from all nodes
        return self._aggregate_reachability_results(reachability_data)

    def _get_upstream_dns_resolvers(self) -> list[str]:
        """
        Get upstream DNS resolvers from DNS operator configuration.

        Queries the dns.operator.openshift.io/cluster resource and extracts
        upstream resolver addresses from spec.upstreamResolvers.upstreams.

        Returns:
            List of DNS server IP addresses (e.g., ['192.168.1.1', '8.8.8.8'])
            Empty list if no upstream resolvers configured
        """
        try:
            _, dns_config_output, _ = self.oc_api.run_oc_command(
                "get", ["dns.operator.openshift.io/cluster", "-o", "json"], timeout=45
            )
        except UnExpectedSystemOutput:
            # DNS operator might not be configured - this is OK, we'll fallback
            return []

        try:
            dns_config = json.loads(dns_config_output)
        except json.JSONDecodeError:
            # Failed to parse - fallback to resolv.conf
            return []

        spec = dns_config.get("spec", {})
        upstream_resolvers = spec.get("upstreamResolvers", {})
        upstreams = upstream_resolvers.get("upstreams", [])

        dns_servers = []
        for upstream in upstreams:
            # Only process Network type upstreams (not SystemResolvConf)
            if upstream.get("type") == "Network":
                address = upstream.get("address")
                if address:
                    dns_servers.append(address)

        return dns_servers

    def _aggregate_reachability_results(self, reachability_data: dict) -> RuleResult:
        """
        Aggregate DNS reachability results from all nodes.

        Args:
            reachability_data: Dictionary of {node_name: {source, reachable, unreachable}}

        Returns:
            RuleResult indicating overall DNS reachability status
        """
        # Aggregate all unique DNS servers and their status across all nodes
        all_reachable = set()
        all_unreachable = set()
        source = None
        per_node_details = []

        for node_name, data in reachability_data.items():
            if not data:
                continue

            # Get source (should be same for all nodes)
            if source is None:
                source = data.get("source", "unknown")

            reachable = data.get("reachable", [])
            unreachable = data.get("unreachable", [])

            # Track per-node details
            if unreachable:
                per_node_details.append(f"{node_name}: {len(unreachable)} unreachable - {', '.join(unreachable)}")

            # Aggregate across all nodes
            all_reachable.update(reachable)
            all_unreachable.update(unreachable)

        # A DNS server is considered unreachable if it's unreachable from ANY node
        truly_unreachable = all_unreachable - all_reachable
        truly_reachable = all_reachable - truly_unreachable

        # Build result message
        if truly_unreachable:
            message = f"DNS servers from {source}:\n"
            if truly_reachable:
                message += f"  Reachable from all nodes ({len(truly_reachable)}):\n"
                for dns_ip in sorted(truly_reachable):
                    message += f"    - {dns_ip}\n"
            message += f"\n  Unreachable from one or more nodes ({len(truly_unreachable)}):\n"
            for dns_ip in sorted(truly_unreachable):
                message += f"    - {dns_ip}\n"

            # Add per-node details
            if per_node_details:
                message += "\n  Per-node details:\n"
                for detail in per_node_details:
                    message += f"    {detail}\n"

            return RuleResult.failed(message.rstrip())

        # All DNS servers are reachable from all nodes
        total_dns_servers = len(truly_reachable)
        message = f"All {total_dns_servers} DNS server(s) from {source} are reachable from all nodes:\n"
        for dns_ip in sorted(truly_reachable):
            message += f"  - {dns_ip}\n"

        return RuleResult.passed(message.rstrip())
