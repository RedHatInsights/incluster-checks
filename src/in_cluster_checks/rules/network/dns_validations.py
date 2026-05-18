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
    Test DNS resolution functionality from each node.

    Tests DNS servers by performing actual DNS lookups using dig.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def collect_data(self, **kwargs) -> dict:
        """
        Test DNS resolution functionality from each node.

        Args:
            **kwargs: 'dns_servers' list - DNS server IPs to test.

        Returns:
            Dictionary with reachability results, or None if no DNS servers provided
            Example: {
                'reachable': ['192.168.1.1'],
                'unreachable': ['8.8.8.8']
            }
        """
        dns_servers = kwargs.get("dns_servers")

        if not dns_servers:
            return None

        reachable = []
        unreachable = []

        for dns_ip in dns_servers:
            # Use dig to test DNS resolution (not just connectivity)
            dig_cmd = SafeCmdString(
                "dig +short +time=2 +tries=1 @{dns_ip} google.com"
            ).format(dns_ip=dns_ip)
            return_code, output, _ = self.run_cmd(dig_cmd)

            # Success if dig returned 0 and produced output (resolved the domain)
            if return_code == 0 and output.strip():
                reachable.append(dns_ip)
            else:
                unreachable.append(dns_ip)

        return {"reachable": reachable, "unreachable": unreachable}


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

        if upstream_dns_servers:
            dns_servers = upstream_dns_servers
            source = "cluster upstream resolvers"
        else:
            # Get DNS servers from /etc/resolv.conf
            dns_servers = self._get_nameservers_from_nodes()
            source = "/etc/resolv.conf"

            if not dns_servers:
                return RuleResult.failed(
                    "No DNS servers found. "
                    "Neither upstream DNS resolvers configured nor nameservers in /etc/resolv.conf."
                )

        # Step 2: Run DNS reachability tests on nodes
        reachability_data = self.run_data_collector(
            DnsReachabilityCollector, dns_servers=dns_servers
        )

        # Check for collection failures
        exceptions = self.get_data_collector_exceptions(DnsReachabilityCollector)
        if exceptions:
            failed_nodes = ", ".join(sorted(exceptions.keys()))
            return RuleResult.failed(
                f"Failed to test DNS reachability from {len(exceptions)} node(s): {failed_nodes}. "
                f"Cannot verify DNS reachability with incomplete data."
            )

        # Aggregate results from all nodes
        return self._aggregate_reachability_results(reachability_data, source)

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

    def _get_nameservers_from_nodes(self) -> list[str]:
        """
        Get nameservers from /etc/resolv.conf on a node.

        Reads /etc/resolv.conf from one node and extracts nameserver entries.

        Returns:
            List of DNS server IP addresses
        """

        # Use DataCollector to read resolv.conf from one node
        class ResolvConfReader(DataCollector):
            objective_hosts = [Objectives.ALL_NODES]

            def collect_data(self, **kwargs) -> list[str]:
                resolv_conf_path = "/etc/resolv.conf"

                if not self.file_utils.is_file_exist(resolv_conf_path):
                    return []

                resolv_conf_content = self.get_output_from_run_cmd(
                    SafeCmdString("cat {path}").format(path=resolv_conf_path)
                )

                nameservers = []
                for line in resolv_conf_content.splitlines():
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            nameservers.append(parts[1])

                return nameservers

        # Collect from nodes
        resolv_data = self.run_data_collector(ResolvConfReader)

        # Return nameservers from first node that has any
        for node_nameservers in resolv_data.values():
            if node_nameservers:
                return node_nameservers

        return []

    def _aggregate_reachability_results(
        self, reachability_data: dict, source: str
    ) -> RuleResult:
        """
        Aggregate DNS reachability results from all nodes.

        Args:
            reachability_data: Dictionary of {node_name: {reachable, unreachable}}
            source: Source of DNS servers (e.g., "cluster upstream resolvers" or "/etc/resolv.conf")

        Returns:
            RuleResult indicating overall DNS reachability status
        """
        # Aggregate all unique DNS servers and their status across all nodes
        all_reachable = set()
        all_unreachable = set()
        per_node_details = []

        for node_name, data in reachability_data.items():
            if not data:
                continue

            reachable = data.get("reachable", [])
            unreachable = data.get("unreachable", [])

            # Track per-node details
            if unreachable:
                per_node_details.append(
                    f"{node_name}: {len(unreachable)} unreachable - {', '.join(unreachable)}"
                )

            # Aggregate across all nodes
            all_reachable.update(reachable)
            all_unreachable.update(unreachable)

        # A DNS server is unreachable only if unreachable from ALL nodes
        truly_unreachable = all_unreachable - all_reachable

        if truly_unreachable:
            unreachable_list = ", ".join(sorted(truly_unreachable))
            return RuleResult.failed(
                f"DNS servers from {source} unreachable from all nodes: {unreachable_list}"
            )

        # All DNS servers reachable from at least one node
        reachable_list = ", ".join(sorted(all_reachable))
        return RuleResult.passed(
            f"All DNS servers from {source} are reachable: {reachable_list}"
        )
