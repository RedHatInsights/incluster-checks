"""
OVN-Kubernetes sanity check validations for OpenShift clusters.

Validates OVN-Kubernetes networking components and logical switch configurations.
Ported from: support/HealthChecks/flows/Network/ovnk8s_sanity_checks.py
"""

import re
from typing import Dict, List, Optional, Tuple

from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.rules.network.ovs_base import OvnDetectingNodeRuleBase
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class OVNKubernetesBase(OrchestratorRule):
    """
    Base class for OVN-Kubernetes validators.

    Provides common functionality for validators that check OVN-Kubernetes
    networking components in OpenShift clusters.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if cluster is using OVN-Kubernetes networking.

        Returns:
            PrerequisiteResult indicating if OVN-Kubernetes is the network type
        """
        try:
            network_obj = self.oc_api.select_resources(resource_type="network.operator/cluster", single=True)
            if not network_obj:
                return PrerequisiteResult.not_met("Cannot determine network type: network.operator/cluster not found")

            network_type = network_obj.model.spec.defaultNetwork.type

            if network_type == "OVNKubernetes":
                return PrerequisiteResult.met()

            return PrerequisiteResult.not_met(f"Cluster is not using OVN-Kubernetes networking (type: {network_type})")
        except Exception as e:
            return PrerequisiteResult.not_met(f"Cannot determine network type: {e}")

    def get_ovn_pod_to_node_dict(self) -> Dict[str, str]:
        """
        Get mapping of ovnkube-node pods to their nodes.

        Returns:
            Dictionary mapping {pod_name: node_name}
        """
        pods = self.oc_api.get_pods(namespace="openshift-ovn-kubernetes", labels={"app": "ovnkube-node"})

        ovn_pod_to_node_dict = {}
        for pod in pods:
            pod_name = pod.name()
            node_name = pod.model.spec.nodeName
            ovn_pod_to_node_dict[pod_name] = node_name

        return ovn_pod_to_node_dict


class NodesHaveOvnkubeNodePod(OVNKubernetesBase):
    """
    Verify each node has an ovnkube-node pod.

    Ensures that every node in the cluster has a corresponding ovnkube-node pod
    running in the openshift-ovn-kubernetes namespace. Missing pods indicate
    networking issues.
    """

    unique_name = "all_nodes_have_ovnkube_node_pod"
    title = "Verify each node has an ovnkube-node pod"

    def run_rule(self) -> RuleResult:
        """
        Check if all nodes have ovnkube-node pods.

        Returns:
            RuleResult indicating if all nodes have ovnkube-node pods
        """
        try:
            # Get all nodes from node executors (no API call needed)
            if not self._node_executors:
                return RuleResult.skip("No node executors available")

            all_nodes = list(self._node_executors.keys())

            # Get nodes with ovnkube pods
            pod_to_node_dict = self.get_ovn_pod_to_node_dict()
            nodes_with_ovnkube_pods = list(pod_to_node_dict.values())

            # Find missing nodes
            missing_nodes = list(set(all_nodes) - set(nodes_with_ovnkube_pods))

            if missing_nodes:
                message = f"The following nodes are missing ovnkube-node pods: {missing_nodes}"
                return RuleResult.failed(message)

            return RuleResult.passed(
                f"All {len(all_nodes)} nodes have ovnkube-node pods ({len(nodes_with_ovnkube_pods)} pods found)"
            )
        except Exception as e:
            return RuleResult.skip(f"Cannot get nodes list: {e}")


class LogicalSwitchNodeValidator(OVNKubernetesBase):
    """
    Validate there is a logical switch with node name for each ovnkube-node.

    Checks that OVN's logical network topology includes a logical switch
    for each node, which is essential for pod networking.
    """

    unique_name = "logical_switch_node_validator"
    title = "Validate there is a logical switch with node name for each ovnkube-node"

    def run_rule(self) -> RuleResult:
        """
        Verify logical switches exist for all ovnkube-node pods.

        Returns:
            RuleResult indicating if logical switches are properly configured
        """
        ovn_pod_to_node_dict = self.get_ovn_pod_to_node_dict()

        if not ovn_pod_to_node_dict:
            return RuleResult.not_applicable("No ovnkube-node pods found")

        failed_checks = []

        for ovnkube_pod, node in ovn_pod_to_node_dict.items():
            # Check if logical switch exists with node name using run_rsh_cmd
            rc, out, err = self.oc_api.run_rsh_cmd(
                namespace="openshift-ovn-kubernetes",
                pod=ovnkube_pod,
                command=SafeCmdString("ovn-nbctl ls-list"),
            )

            if rc != 0:
                failed_checks.append(f"ovnkube-node {ovnkube_pod}: cannot execute ovn-nbctl ls-list - {err}")
                continue

            # Check if node name appears in logical switch list
            if f"({node})" not in out:
                failed_checks.append(f"ovnkube-node {ovnkube_pod}: there is no logical switch with node name - {node}")

        if failed_checks:
            message = "\n".join(failed_checks)
            return RuleResult.failed(message)

        return RuleResult.passed(
            f"All {len(ovn_pod_to_node_dict)} ovnkube-node pods have corresponding logical switches"
        )


class MTUOverlayInterfaces(OVNKubernetesBase):
    """
    Validate MTU overlay interfaces.

    Checks that overlay network interfaces (ovn-k8s-mp0, br-int) on each
    ovnkube-node pod have the correct MTU as configured in the Network CR
    (network.operator/cluster). Tunnel devices (geneve, vxlan) are excluded as
    they use kernel default MTU values. MTU mismatches can cause packet drops
    and connectivity issues.
    """

    OVERLAY_KEYWORDS = ["ovn", "br-int"]

    unique_name = "MTU_overlay_interfaces_validator"
    title = "Validate MTU overlay interfaces"

    def run_rule(self) -> RuleResult:
        ovn_pod_to_node_dict = self.get_ovn_pod_to_node_dict()

        if not ovn_pod_to_node_dict:
            return RuleResult.not_applicable("No ovnkube-node pods found")

        expected_mtu = self._get_expected_mtu()
        if expected_mtu is None:
            return RuleResult.skip("Cannot determine expected MTU from network.operator/cluster")

        failed_checks = []
        for ovnkube_pod in ovn_pod_to_node_dict:
            rc, out, err = self.oc_api.run_rsh_cmd(
                namespace="openshift-ovn-kubernetes",
                pod=ovnkube_pod,
                command=SafeCmdString("ip link show"),
            )

            if rc != 0:
                failed_checks.append(f"[OVNKube Node: {ovnkube_pod}] Failed to run ip link show: {err}")
                continue

            overlay_interfaces = self._parse_overlay_interfaces(out)

            if not overlay_interfaces:
                failed_checks.append(f"[OVNKube Node: {ovnkube_pod}] No overlay network interfaces found")
                continue

            for interface, actual_mtu in overlay_interfaces:
                if expected_mtu != actual_mtu:
                    failed_checks.append(
                        f"[OVNKube Node: {ovnkube_pod}] MTU Mismatch: "
                        f"Expected (Network CR) = {expected_mtu}, Actual ({interface}) = {actual_mtu}"
                    )

        if failed_checks:
            return RuleResult.failed("\n".join(failed_checks))

        return RuleResult.passed()

    def _get_expected_mtu(self) -> Optional[int]:
        network_obj = self.oc_api.select_resources(
            resource_type="network.operator/cluster",
            single=True,
        )

        if not network_obj:
            return None

        try:
            return int(network_obj.model.spec.defaultNetwork.ovnKubernetesConfig.mtu)
        except Exception:
            return None

    def _parse_overlay_interfaces(self, ip_link_output: str) -> List[Tuple[str, int]]:
        results = []
        for line in ip_link_output.splitlines():
            if any(keyword in line for keyword in self.OVERLAY_KEYWORDS) and "mtu" in line:
                try:
                    interface = line.split()[1].split(":")[0]
                    actual_mtu = int(line.split("mtu ")[1].split()[0])
                    results.append((interface, actual_mtu))
                except (IndexError, ValueError):
                    continue
        return results


class OvnRoutingHealthCheck(OvnDetectingNodeRuleBase):
    """
    Verify OVN-learned routes are present in routing table.

    Validates that routing table contains routes via OVN interfaces
    (ovn-k8s-mp0), which are essential for pod-to-pod communication
    and cluster networking.

    RCA symptom: "node not able to reach openshift API. Therefore the nodes
                  remains in 'NotReady' state"
    """

    unique_name = "ovn_routing_health_check"
    title = "Verify OVN-learned routes are present"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-OVN-Routing-Health-Check",
    ]

    def _run_ovn_rule(self) -> RuleResult:
        """
        Check for OVN routes in routing table.

        Returns:
            RuleResult indicating routing health status
        """
        routes = self.get_output_from_run_cmd(SafeCmdString("ip route show"))

        # Check for OVN management interface (ovn-k8s-mp<N>)
        # Pattern matches ovn-k8s-mp0, ovn-k8s-mp1, etc.
        ovn_interfaces = re.findall(r"ovn-k8s-mp\d+", routes)

        if not ovn_interfaces:
            return RuleResult.failed(
                "No routes via OVN management interface found. "
                "Expected routes via ovn-k8s-mp<N> interface (e.g., ovn-k8s-mp0)"
            )

        # Report which interface(s) found
        interface_list = ", ".join(sorted(set(ovn_interfaces)))
        return RuleResult.passed(f"OVN routes are present (routes via {interface_list} found)")
