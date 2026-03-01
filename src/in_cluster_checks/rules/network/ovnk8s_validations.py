"""
OVN-Kubernetes sanity check validations for OpenShift clusters.

Validates OVN-Kubernetes networking components and logical switch configurations.
Ported from: support/HealthChecks/flows/Network/ovnk8s_sanity_checks.py
"""

from typing import Dict

from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives


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
            network_obj = self._select_resources(resource_type="network.operator/cluster", single=True)
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
        pods = self._get_pods(namespace="openshift-ovn-kubernetes", labels={"app": "ovnkube-node"})

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
            return RuleResult.skip("No ovnkube-node pods found")

        failed_checks = []

        for ovnkube_pod, node in ovn_pod_to_node_dict.items():
            # Check if logical switch exists with node name using run_rsh_cmd
            rc, out, err = self.run_rsh_cmd(
                namespace="openshift-ovn-kubernetes",
                pod=ovnkube_pod,
                command="ovn-nbctl ls-list",
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
