"""
DNS reachability validations for OpenShift clusters.

Validates DNS server reachability by checking upstream DNS resolvers
and testing DNS resolution functionality using dig.
"""

import json
from typing import ClassVar

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.core.rule_result import PrerequisiteResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DnsReachabilityCollector(DataCollector):
    """
    Test DNS resolution functionality from each node.

    Tests DNS servers by performing actual DNS lookups using dig.
    """

    objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]

    def collect_data(self, **kwargs) -> dict:
        """
        Test DNS resolution functionality from each node.

        Args:
            **kwargs:
                'dns_servers' (list): DNS server IPs to test.
                'test_domain' (str): Domain name to use for DNS resolution test.

        Returns:
            Dictionary with reachability results, or None if no DNS servers provided.
            Example: {
                'reachable': ['192.168.1.1'],
                'unreachable': ['8.8.8.8']
            }
        """
        dns_servers = kwargs.get("dns_servers")
        test_domain = kwargs.get("test_domain")

        if not dns_servers or not test_domain:
            return None

        reachable = []
        unreachable = []

        for dns_ip in dns_servers:
            # Use dig to test DNS resolution (not just connectivity)
            dig_cmd = SafeCmdString("dig +short +time=2 +tries=1 @{dns_ip} {domain}").format(
                dns_ip=dns_ip, domain=test_domain
            )
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
    4. Uses the search domain from /etc/resolv.conf for DNS resolution tests
    5. Reports which DNS servers are reachable/unreachable

    Orchestrator-level validator that coordinates DNS checks across the cluster.
    """

    objective_hosts: ClassVar[list] = [Objectives.ORCHESTRATOR]
    unique_name = "verify_dns_reachability"
    title = "Verify DNS server reachability"
    links: ClassVar[list] = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Network-%E2%80%90-Verify-DNS-reachability",
    ]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if dig binary is available on the nodes.

        Returns:
            PrerequisiteResult indicating if dig is available
        """

        # Check dig availability on one node
        class DigChecker(DataCollector):
            """Check if dig binary is available on nodes."""

            objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]

            def collect_data(self, **kwargs) -> bool:
                """
                Check if dig command is available.

                Returns:
                    bool: True if dig is available, False otherwise
                """
                return_code, _, _ = self.run_cmd("which dig")
                return return_code == 0

        dig_availability = self.run_data_collector(DigChecker)

        # If dig is not available on any node, prerequisite not met
        if not any(dig_availability.values()):
            return PrerequisiteResult.not_met("dig binary not available on nodes")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Check DNS server reachability.

        Returns:
            RuleResult indicating DNS reachability status
        """
        # Step 1: Try to get upstream DNS resolvers from cluster DNS operator config
        upstream_dns_servers = self._get_upstream_dns_resolvers()

        if upstream_dns_servers:
            dns_servers = upstream_dns_servers
            source = "DNS operator upstream resolvers"
        else:
            # Get DNS servers from /etc/resolv.conf
            dns_servers = self._get_nameservers_from_nodes()
            source = "/etc/resolv.conf"

            if not dns_servers:
                return RuleResult.failed(
                    "No DNS servers found. "
                    "Neither upstream DNS resolvers configured nor nameservers in /etc/resolv.conf."
                )

        # Step 2: Get search domain from /etc/resolv.conf for DNS resolution test
        search_domain = self._get_search_domain_from_nodes()
        if not search_domain:
            # Fallback to a reasonable default if no search domain found
            search_domain = "openshift.svc.cluster.local"

        # Step 3: Run DNS reachability tests on nodes
        reachability_data = self.run_data_collector(
            DnsReachabilityCollector,
            dns_servers=dns_servers,
            test_domain=search_domain,
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

        Raises:
            UnExpectedSystemOutput: If DNS operator query fails with error
        """
        return_code, dns_config_output, stderr = self.oc_api.run_oc_command(
            "get", ["dns.operator.openshift.io/cluster", "-o", "json"], timeout=45
        )

        # If DNS operator resource doesn't exist, return empty list (not an error)
        if return_code != 0:
            if "NotFound" in stderr or "not found" in stderr.lower():
                return []
            # Other errors should propagate
            raise UnExpectedSystemOutput(f"Failed to query DNS operator config: {stderr}")

        # Parse DNS config
        try:
            dns_config = json.loads(dns_config_output)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(f"Failed to parse DNS operator config JSON: {e}")

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
        Get nameservers from /etc/resolv.conf across all nodes.

        Reads /etc/resolv.conf from all nodes and aggregates unique nameserver entries.

        Returns:
            List of unique DNS server IP addresses from all nodes
        """

        # Use DataCollector to read resolv.conf from all nodes
        class ResolvConfReader(DataCollector):
            """Read nameservers from /etc/resolv.conf on all nodes."""

            objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]

            def collect_data(self, **kwargs) -> list[str]:
                """
                Extract nameserver entries from /etc/resolv.conf.

                Returns:
                    list[str]: List of nameserver IP addresses
                """
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

        # Collect from all nodes
        resolv_data = self.run_data_collector(ResolvConfReader)

        # Aggregate unique nameservers from all nodes
        all_nameservers = set()
        for node_nameservers in resolv_data.values():
            if node_nameservers:
                all_nameservers.update(node_nameservers)

        return sorted(all_nameservers)

    def _get_search_domain_from_nodes(self) -> str:
        """
        Get search domain from /etc/resolv.conf on nodes.

        Reads /etc/resolv.conf from one node and extracts the search domain.
        Uses the internal domain for DNS resolution tests in disconnected environments.

        Returns:
            Search domain string (e.g., 'cluster-name.base-domain.com'),
            or empty string if not found
        """

        # Use DataCollector to read resolv.conf and extract search domain
        class SearchDomainReader(DataCollector):
            """Extract search domain from /etc/resolv.conf on nodes."""

            objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]

            def collect_data(self, **kwargs) -> str:
                """
                Extract the search domain from /etc/resolv.conf.

                Returns:
                    str: First search domain found, or empty string if none exists
                """
                resolv_conf_path = "/etc/resolv.conf"

                if not self.file_utils.is_file_exist(resolv_conf_path):
                    return ""

                resolv_conf_content = self.get_output_from_run_cmd(
                    SafeCmdString("cat {path}").format(path=resolv_conf_path)
                )

                # Look for search domain line
                for line in resolv_conf_content.splitlines():
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    if line.startswith("search"):
                        parts = line.split()
                        # Return first search domain
                        if len(parts) >= 2:
                            return parts[1]

                return ""

        # Collect from nodes
        search_data = self.run_data_collector(SearchDomainReader)

        # Return search domain from first node that has one
        for node_search_domain in search_data.values():
            if node_search_domain:
                return node_search_domain

        return ""

    def _aggregate_reachability_results(self, reachability_data: dict, source: str) -> RuleResult:
        """
        Aggregate DNS reachability results from all nodes.

        Args:
            reachability_data: Dictionary of {node_name: {reachable, unreachable}}
            source: Source of DNS servers (e.g., "DNS operator upstream resolvers" or "/etc/resolv.conf")

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

            # Track per-node details for unreachable servers
            if unreachable:
                per_node_details.append(f"  - {node_name}: {', '.join(unreachable)}")

            # Aggregate across all nodes
            all_reachable.update(reachable)
            all_unreachable.update(unreachable)

        # Compute three disjoint sets:
        # - only_unreachable: unreachable from ALL nodes (intersection)
        # - only_reachable: reachable from ALL nodes
        # - partial: reachable from SOME nodes, unreachable from others
        only_unreachable = all_unreachable - all_reachable
        partial = all_reachable & all_unreachable

        # FAIL: Some DNS servers unreachable from all nodes
        if only_unreachable:
            unreachable_list = ", ".join(sorted(only_unreachable))
            details = "\n".join(per_node_details) if per_node_details else ""
            msg = f"DNS servers from {source} unreachable from all nodes: {unreachable_list}"
            if details:
                msg += f"\nPer-node details:\n{details}"
            return RuleResult.failed(msg)

        # WARNING: Some DNS servers have partial reachability
        if partial:
            partial_list = ", ".join(sorted(partial))
            details = "\n".join(per_node_details)
            return RuleResult.warning(
                f"DNS servers from {source} have partial reachability: {partial_list}\n"
                f"Reachable from some nodes but not all.\n"
                f"Per-node details:\n{details}"
            )

        # PASS: All DNS servers reachable from all nodes
        reachable_list = ", ".join(sorted(all_reachable))
        return RuleResult.passed(f"All DNS servers from {source} are reachable from all nodes: {reachable_list}")
