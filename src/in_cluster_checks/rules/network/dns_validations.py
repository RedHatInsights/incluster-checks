from typing import ClassVar

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import OrchestratorDataCollector
from in_cluster_checks.core.rule import Rule, RuleResult
from in_cluster_checks.core.rule_result import PrerequisiteResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_json
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
        dns_config = parse_json(
            dns_config_output,
            "oc get dns.operator.openshift.io/cluster -o json",
            self.get_host_ip(),
        )

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

    This validation checks if DNS servers are reachable via ICMP ping:
    1. Gets DNS servers from cluster DNS operator config
    2. If not found, reads DNS servers from /etc/resolv.conf on this node
    3. Tests if each DNS server is reachable via ping
    4. Reports which DNS servers are reachable/unreachable from this node
    """

    objective_hosts: ClassVar[list] = [Objectives.ALL_NODES]
    supported_profiles: ClassVar[set] = {"general"}
    unique_name = "verify_dns_reachability"
    title = "Verify DNS server reachability"
    links: ClassVar[list] = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418450933/Verify+DNS+reachability",
    ]
    RESOLV_CONF_PATH = "/etc/resolv.conf"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if ping binary is available on this node.

        Returns:
            PrerequisiteResult indicating if ping is available
        """
        return_code, _, _ = self.run_cmd(SafeCmdString("which ping"))
        if return_code != 0:
            return PrerequisiteResult.not_met("ping binary not available on this node")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Check DNS server reachability from this node.

        Returns:
            RuleResult indicating DNS reachability status for this node
        """
        # Get DNS servers from DNS operator config (shared across all nodes)
        dns_operator_config = self.run_data_collector(DnsOperatorConfigCollector)
        # dns_operator_config is dict: {orchestrator_ip: [dns_servers]}

        # Handle empty dict case (no orchestrators returned data)
        dns_servers = next(iter(dns_operator_config.values()), [])

        # Validate DNS configuration consistency across orchestrators
        if dns_operator_config:
            dns_configs_set = {tuple(sorted(servers)) for servers in dns_operator_config.values()}
            if len(dns_configs_set) > 1:
                # Configuration mismatch - report which orchestrators have different configs
                config_details = []
                for orch_ip, servers in dns_operator_config.items():
                    config_details.append(f"{orch_ip}: {', '.join(servers) if servers else '(empty)'}")
                return RuleResult.failed(
                    "DNS configuration mismatch across orchestrators:\n" + "\n".join(config_details)
                )

        if dns_servers:
            source = "DNS operator upstream resolvers"
        else:
            # Read DNS servers from local /etc/resolv.conf on this node
            dns_servers = self._get_local_nameservers()
            source = self.RESOLV_CONF_PATH

        if not dns_servers:
            return RuleResult.failed(f"No DNS servers found at {source}")

        # Test DNS server reachability
        reachable = []
        unreachable = []

        for dns_server in dns_servers:
            # Simple connectivity check - ping DNS server with 1 packet, 2 second timeout
            ping_cmd = SafeCmdString("ping -c 1 -W 2 {dns_ip}").format(dns_ip=dns_server)
            return_code, _, _ = self.run_cmd(ping_cmd)

            # Success if ping returned 0 (DNS server responded to ICMP)
            if return_code == 0:
                reachable.append(dns_server)
            else:
                unreachable.append(dns_server)

        # Return result for this node
        if unreachable:
            unreachable_list = ", ".join(unreachable)
            return RuleResult.failed(f"Following DNS servers from {source} unreachable: {unreachable_list}")

        reachable_list = ", ".join(reachable)
        return RuleResult.passed(f"All DNS servers from {source} are reachable: {reachable_list}")

    def _get_local_nameservers(self) -> list[str]:
        """
        Read nameservers from /etc/resolv.conf on this node.

        Excludes the node's own IP addresses from the list, as they would
        be self-referential and not useful for DNS reachability testing.

        Returns:
            List of nameserver IP addresses excluding node's own IPs
        """
        if not self.file_utils.is_file_exist(self.RESOLV_CONF_PATH):
            return []

        resolv_conf_content = self.get_output_from_run_cmd(
            SafeCmdString("cat {path}").format(path=self.RESOLV_CONF_PATH)
        )

        # Get node's own IP addresses to exclude them
        node_ips = self._get_node_ips()

        nameservers = []
        for line in resolv_conf_content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    nameserver_ip = parts[1]
                    # Exclude node's own IP addresses
                    if nameserver_ip not in node_ips:
                        nameservers.append(nameserver_ip)

        return nameservers

    def _get_node_ips(self) -> list[str]:
        """
        Get all IP addresses of this node.

        Returns:
            List of IP addresses for this node
        """
        return_code, output, _ = self.run_cmd(SafeCmdString("hostname -I"))
        if return_code != 0 or not output:
            return []

        # hostname -I returns space-separated IPs
        return output.strip().split()
