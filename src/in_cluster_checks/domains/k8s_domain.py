"""
Kubernetes/OpenShift rule domain.

Orchestrates K8s/OpenShift-related healthcheck validators.
Based on HealthChecks/flows/K8s/k8s_components/K8s_flow.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.k8s.k8s_validations import (  # AllPodsReadyAndRunning disabled (PDRIVE-806)
    AllDeploymentsAvailable,
    AllStatefulsetsReady,
    CheckDeploymentsReplicaStatus,
    InfraPodsReadyAndRunning,
    NodesAreReady,
    NodesCpuAndMemoryStatus,
    OpenshiftOperatorStatus,
    ValidateAllDaemonsetsScheduled,
    ValidateAllPoliciesCompliant,
    ValidateNamespaceStatus,
    VerifyClusterOperatorsAvailable,
    VerifyFARControllerReplicas,
    VerifyInternalRegistry,
    VerifyNetworkDiagnosticsDisabled,
    VerifyWebConsoleDisabled,
)
from in_cluster_checks.rules.k8s.subscription_operator_validations import (
    VerifyAcmOperatorHealth,
    VerifyFarContainerNonRoot,
    VerifyNfdOperatorHealth,
    VerifyNfdPodRestartCount,
    VerifyWorkloadAvailabilityNamespaceHealth,
)


class K8sValidationDomain(RuleDomain):
    """
    Kubernetes/OpenShift rule domain.

    Validates cluster health from K8s perspective (pods, nodes, namespaces, etc.).
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "k8s"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of K8s validators to run.

        Returns:
            List of Rule classes
        """
        return [
            # AllPodsReadyAndRunning,  # Disabled: replaced by InfraPodsReadyAndRunning (PDRIVE-806)
            InfraPodsReadyAndRunning,
            NodesAreReady,
            NodesCpuAndMemoryStatus,
            ValidateNamespaceStatus,
            ValidateAllDaemonsetsScheduled,
            AllDeploymentsAvailable,
            CheckDeploymentsReplicaStatus,
            AllStatefulsetsReady,
            OpenshiftOperatorStatus,
            ValidateAllPoliciesCompliant,
            VerifyClusterOperatorsAvailable,
            VerifyInternalRegistry,
            VerifyWebConsoleDisabled,
            VerifyNetworkDiagnosticsDisabled,
            VerifyNfdOperatorHealth,
            VerifyNfdPodRestartCount,
            VerifyAcmOperatorHealth,
            VerifyWorkloadAvailabilityNamespaceHealth,
            VerifyFARControllerReplicas,
            VerifyFarContainerNonRoot,
        ]
