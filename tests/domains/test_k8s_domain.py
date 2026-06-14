"""Tests for K8s validation domain."""

from in_cluster_checks.domains.k8s_domain import K8sValidationDomain
from in_cluster_checks.rules.k8s.k8s_validations import (
    AllPodsReadyAndRunning,
    NodesAreReady,
    NodesCpuAndMemoryStatus,
    OpenshiftOperatorStatus,
    ValidateAllDaemonsetsScheduled,
    ValidateAllPoliciesCompliant,
    ValidateNamespaceStatus,
    VerifyAcmOperatorHealth,
    VerifyClusterOperatorsAvailable,
    VerifyFarContainerNonRoot,
    VerifyFARControllerReplicas,
    VerifyFarOperatorHealth,
    VerifyInternalRegistry,
    VerifyNetworkDiagnosticsDisabled,
    VerifyNfdOperatorHealth,
    VerifyNfdPodRestartCount,
    VerifyNmoOperatorHealth,
    VerifyWebConsoleDisabled,
)


def test_k8s_domain_name():
    """Test domain name."""
    domain = K8sValidationDomain()
    assert domain.domain_name() == "k8s"


def test_k8s_domain_rules():
    """Test domain returns correct rules."""
    domain = K8sValidationDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 21
    assert AllPodsReadyAndRunning in rules
    assert NodesAreReady in rules
    assert NodesCpuAndMemoryStatus in rules
    assert ValidateNamespaceStatus in rules
    assert ValidateAllDaemonsetsScheduled in rules
    assert OpenshiftOperatorStatus in rules
    assert ValidateAllPoliciesCompliant in rules
    assert VerifyClusterOperatorsAvailable in rules
    assert VerifyFarContainerNonRoot in rules
    assert VerifyFARControllerReplicas in rules
    assert VerifyInternalRegistry in rules
    assert VerifyWebConsoleDisabled in rules
    assert VerifyNetworkDiagnosticsDisabled in rules
    assert VerifyNfdOperatorHealth in rules
    assert VerifyNfdPodRestartCount in rules
    assert VerifyAcmOperatorHealth in rules
    assert VerifyNmoOperatorHealth in rules
    assert VerifyFarOperatorHealth in rules
