import json
from typing import ClassVar

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import OrchestratorDataCollector
from in_cluster_checks.core.rule import Rule, RuleResult
from in_cluster_checks.core.rule_result import PrerequisiteResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DnsOperatorConfigCollector(OrchestratorDataCollector):
    """
    Fetch upstream DNS servers from DNS operator configuration.

    Queries the dns.operator.openshift.io/cluster resource and extracts
    upstream resolver addresses.
    """

    objective_hosts: ClassVar[list] = [Objectives.ORCHESTRATOR]

    def collect_data(self, **kwargs) -> list[str]:
        """
        Get upstream DNS resolvers from DNS operator configuration.

        Returns:
            List of DNS server IP addresses or empty list if not configured
        """
        try:
            return_code, dns_config_output, stderr = self.oc_api.run_oc_command(
                "get", ["dns.operator.openshift.io/cluster", "-o", "json"], timeout=45
            )
        except UnExpectedSystemOutput as e:
            # DNS operator might not exist - check if it's a NotFound error
            error_msg = str(e).lower()
            if "notfound" in error_msg or "not found" in error_msg:
                return []
            # Other errors should propagate
            raise

        # If DNS operator resource doesn't exist, return empty list
        if return_code != 0:
            # Check both stdout and stderr for NotFound (can appear in either)
            combined_output = f"{dns_config_output} {stderr}"
            if "NotFound" in combined_output or "not found" in combined_output.lower():
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


class VerifyDnsReachability(Rule):
    """
    Verify DNS server reachability.

    This validation checks:
    1. Looks for upstream DNS resolvers in the cluster DNS operator config
    2. If found, tests those DNS servers from this node
    3. If not configured, checks /etc/resolv.conf on this node and tests those DNS servers
    4. Uses the search domain from /etc/resolv.conf for DNS resolution tests
    5. Reports which DNS servers are reachable/unreachable from this node
    """

    objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]
    supported_profiles: ClassVar[set] = {"general"}
    unique_name = "verify_dns_reachability"
    title = "Verify DNS server reachability"
    links: ClassVar[list] = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/Network-%E2%80%90-Verify-DNS-reachability",
    ]
    RESOLV_CONF_PATH = "/etc/resolv.conf"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if dig binary is available on this node.

        Returns:
            PrerequisiteResult indicating if dig is available
        """
        return_code, _, _ = self.run_cmd("which dig")
        if return_code != 0:
            return PrerequisiteResult.not_met("dig binary not available on this node")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Check DNS server reachability from this node.

        Returns:
            RuleResult indicating DNS reachability status for this node
        """
        # Get DNS servers from DNS operator config (shared across all nodes)
        dns_operator_config = self.get_data_from_collector(DnsOperatorConfigCollector)

        if dns_operator_config:
            dns_servers = dns_operator_config
            source = "DNS operator upstream resolvers"
        else:
            # Read DNS servers from local /etc/resolv.conf on this node
            dns_servers = self._get_local_nameservers()
            source = "/etc/resolv.conf"

        if not dns_servers:
            return RuleResult.failed("No DNS servers found")

        # Get search domain for DNS resolution test
        search_domain = self._get_local_search_domain()
        if not search_domain:
            search_domain = "openshift.svc.cluster.local"

        # Test DNS resolution for each server
        reachable = []
        unreachable = []

        for dns_server in dns_servers:
            dig_cmd = SafeCmdString("dig +short +time=2 +tries=1 @{dns_ip} {domain}").format(
                dns_ip=dns_server, domain=search_domain
            )
            return_code, _, _ = self.run_cmd(dig_cmd)

            # Success if dig returned 0 (DNS server responded)
            if return_code == 0:
                reachable.append(dns_server)
            else:
                unreachable.append(dns_server)

        # Return result for this node
        if unreachable:
            unreachable_list = ", ".join(unreachable)
            return RuleResult.failed(f"DNS servers from {source} unreachable: {unreachable_list}")

        reachable_list = ", ".join(reachable)
        return RuleResult.passed(f"All DNS servers from {source} are reachable: {reachable_list}")

    def _get_local_nameservers(self) -> list[str]:
        """
        Read nameservers from /etc/resolv.conf on this node.

        Returns:
            List of nameserver IP addresses
        """
        if not self.file_utils.is_file_exist(self.RESOLV_CONF_PATH):
            return []

        resolv_conf_content = self.get_output_from_run_cmd(
            SafeCmdString("cat {path}").format(path=self.RESOLV_CONF_PATH)
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

    def _get_local_search_domain(self) -> str:
        """
        Extract search domain from /etc/resolv.conf on this node.

        Returns:
            First search domain found, or empty string
        """
        if not self.file_utils.is_file_exist(self.RESOLV_CONF_PATH):
            return ""

        resolv_conf_content = self.get_output_from_run_cmd(
            SafeCmdString("cat {path}").format(path=self.RESOLV_CONF_PATH)
        )

        for line in resolv_conf_content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if line.startswith("search"):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]

        return ""
