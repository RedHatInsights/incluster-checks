"""
Tests for subscription operator validations.

Validates health and status of subscription operators.
"""

import json
from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.k8s.subscription_operator_validations import (
    VerifyAcmOperatorHealth,
    VerifyFarContainerNonRoot,
    VerifyNfdOperatorHealth,
    VerifyNfdPodRestartCount,
    VerifyWorkloadAvailabilityNamespaceHealth,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def create_mock_pod(namespace, name, phase, all_containers_ready=True):
    """Create a mock pod object."""
    mock_pod = Mock()
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": namespace, "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": [{"ready": all_containers_ready}],
        },
    }
    return mock_pod


def _nfd_subscriptions(include_nfd=True):
    """Build a subscriptions response, optionally including the nfd subscription."""
    items = []
    if include_nfd:
        items.append(
            {
                "metadata": {"name": "nfd-sub", "namespace": VerifyNfdOperatorHealth.NFD_NAMESPACE},
                "spec": {"name": "nfd", "source": "redhat-operators"},
            }
        )
    items.append(
        {
            "metadata": {"name": "other-operator", "namespace": "openshift-operators"},
            "spec": {"name": "other", "source": "redhat-operators"},
        }
    )
    return {"items": items}


class TestVerifyNfdOperatorHealth(RuleTestBase):
    """Test VerifyNfdOperatorHealth rule."""

    tested_type = VerifyNfdOperatorHealth

    scenario_passed = [
        RuleScenarioParams(
            "NFD operator installed and all pods are healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-controller-manager-abc123", "Running"),
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-worker-xyz789", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "NFD operator subscription not found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=False))),
            },
        ),
        RuleScenarioParams(
            "no subscriptions exist in cluster",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps({"items": []})),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "NFD operator installed but no pods found",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(return_value=[]),
            },
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            failed_msg="No pods found in openshift-nfd namespace.",
        ),
        RuleScenarioParams(
            "NFD operator installed but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-controller-manager-abc123", "Running"),
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-worker-xyz789", "Pending"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            failed_msg="Unhealthy pods in openshift-nfd namespace:\n"
            "  nfd-worker-xyz789 - Phase: Pending",
        ),
        RuleScenarioParams(
            "NFD operator installed but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-controller-manager-abc123", "Running", False),
                    ]
                ),
            },
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            failed_msg="Unhealthy pods in openshift-nfd namespace:\n"
            "  nfd-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "NFD operator installed but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyNfdOperatorHealth.NFD_NAMESPACE, "nfd-controller-manager-abc123", "Succeeded"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            failed_msg="Pods in unexpected succeeded state in openshift-nfd namespace:\n"
            "  nfd-controller-manager-abc123",
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NFD operator subscription found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when NFD operator is installed."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when NFD operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when all NFD pods are healthy."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when NFD pods are unhealthy or missing."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


def _create_mock_nfd_restart_pod(name, container_statuses, init_container_statuses=None):
    """Create a mock NFD pod object for restart count tests."""
    mock_pod = Mock()
    mock_pod.name.return_value = name
    status = {"containerStatuses": container_statuses}
    if init_container_statuses:
        status["initContainerStatuses"] = init_container_statuses
    mock_pod.as_dict.return_value = {
        "metadata": {"name": name, "namespace": VerifyNfdOperatorHealth.NFD_NAMESPACE},
        "status": status,
    }
    return mock_pod


_NFD_RESTART_SUB_CMD = ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"))


class TestVerifyNfdPodRestartCount(RuleTestBase):
    """Test VerifyNfdPodRestartCount rule."""

    tested_type = VerifyNfdPodRestartCount

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NFD operator subscription found",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "NFD operator subscription not found",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=False))),
            },
        ),
        RuleScenarioParams(
            "no subscriptions exist in cluster",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps({"items": []})),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "NFD pods have zero restart count",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_mock_nfd_restart_pod(
                            "nfd-controller-manager-abc123",
                            [{"name": "manager", "restartCount": 0, "ready": True}],
                        ),
                        _create_mock_nfd_restart_pod(
                            "nfd-worker-xyz789",
                            [{"name": "nfd-worker", "restartCount": 0, "ready": True}],
                        ),
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "NFD pods with init containers all zero restarts",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_mock_nfd_restart_pod(
                            "nfd-controller-manager-abc123",
                            [{"name": "manager", "restartCount": 0, "ready": True}],
                            init_container_statuses=[{"name": "init-setup", "restartCount": 0, "ready": True}],
                        ),
                    ]
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "NFD pods not found in namespace",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(return_value=[]),
            },
            failed_msg="No pods found in openshift-nfd namespace. NFD operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "NFD pod has non-zero restart count",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_mock_nfd_restart_pod(
                            "nfd-controller-manager-abc123",
                            [{"name": "manager", "restartCount": 0, "ready": True}],
                        ),
                        _create_mock_nfd_restart_pod(
                            "nfd-worker-xyz789",
                            [{"name": "nfd-worker", "restartCount": 3, "ready": True}],
                        ),
                    ]
                ),
            },
            failed_msg="NFD pods in openshift-nfd namespace have non-zero restart counts:\n"
            "  nfd-worker-xyz789/nfd-worker: restartCount=3",
        ),
        RuleScenarioParams(
            "Multiple NFD pods with restarts across containers",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_mock_nfd_restart_pod(
                            "nfd-controller-manager-abc123",
                            [{"name": "manager", "restartCount": 2, "ready": True}],
                        ),
                        _create_mock_nfd_restart_pod(
                            "nfd-worker-xyz789",
                            [{"name": "nfd-worker", "restartCount": 5, "ready": True}],
                        ),
                    ]
                ),
            },
            failed_msg="NFD pods in openshift-nfd namespace have non-zero restart counts:\n"
            "  nfd-controller-manager-abc123/manager: restartCount=2\n"
            "  nfd-worker-xyz789/nfd-worker: restartCount=5",
        ),
        RuleScenarioParams(
            "NFD init container has non-zero restart count",
            oc_cmd_output_dict={
                _NFD_RESTART_SUB_CMD: CmdOutput(json.dumps(_nfd_subscriptions(include_nfd=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_mock_nfd_restart_pod(
                            "nfd-controller-manager-abc123",
                            [{"name": "manager", "restartCount": 0, "ready": True}],
                            init_container_statuses=[{"name": "init-setup", "restartCount": 1, "ready": True}],
                        ),
                    ]
                ),
            },
            failed_msg="NFD pods in openshift-nfd namespace have non-zero restart counts:\n"
            "  nfd-controller-manager-abc123/init-setup: restartCount=1",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when NFD operator is installed."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when NFD operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when all NFD pods have zero restart count."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when NFD pods have non-zero restart counts."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)



def _acm_subscriptions(include_acm=True, installed_csv="advanced-cluster-management.v2.12.0"):
    """Build a subscriptions response, optionally including the ACM subscription."""
    items = []
    if include_acm:
        sub = {
            "metadata": {"name": "acm-sub", "namespace": VerifyAcmOperatorHealth.ACM_NAMESPACE},
            "spec": {
                "name": "advanced-cluster-management",
                "source": "redhat-operators",
            },
        }
        if installed_csv:
            sub["status"] = {"installedCSV": installed_csv}
        items.append(sub)
    items.append(
        {
            "metadata": {"name": "other-operator", "namespace": "openshift-operators"},
            "spec": {"name": "other", "source": "redhat-operators"},
        }
    )
    return {"items": items}


def _acm_csv_response(include_csv=True, phase="Succeeded"):
    """Build a ClusterServiceVersion list response for ACM."""
    items = []
    if include_csv:
        reason = "InstallSucceeded" if phase == "Succeeded" else "InstallFailed"
        message = "install strategy completed with no errors" if phase == "Succeeded" else "install failed"
        items.append(
            {
                "metadata": {
                    "name": "advanced-cluster-management.v2.12.0",
                    "namespace": "open-cluster-management",
                },
                "status": {
                    "phase": phase,
                    "reason": reason,
                    "message": message,
                },
            }
        )
    return {"items": items}


_ACM_SUB_CMD = (
    "get",
    ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"),
)
_ACM_CSV_CMD = ("get", ("csv", "-n", "open-cluster-management", "-o", "json"))


class TestVerifyAcmOperatorHealth(RuleTestBase):
    """Test VerifyAcmOperatorHealth rule."""

    tested_type = VerifyAcmOperatorHealth

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "ACM operator subscription found",
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "ACM operator installed, CSV succeeded via installedCSV, and all pods are healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running"),
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "cluster-manager-xyz789", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
        ),
        RuleScenarioParams(
            "ACM operator installed, CSV succeeded via pattern fallback (no installedCSV)",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True, installed_csv=None))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
        ),
        RuleScenarioParams(
            "ACM operator passes with Succeeded (completed job) pods ignored",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running"),
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "acm-init-job-xyz789", "Succeeded"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "ACM operator subscription not found",
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=False))),
            },
        ),
        RuleScenarioParams(
            "no subscriptions exist in cluster",
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps({"items": []})),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ACM CSV not found in namespace",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response(include_csv=False))),
            },
            failed_msg=(
                "No ClusterServiceVersion matching 'advanced-cluster-management' "
                "found in open-cluster-management namespace"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV in Failed phase",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod("open-cluster-management", "multiclusterhub-operator-abc123", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response(phase="Failed"))),
            },
            failed_msg=(
                "ACM ClusterServiceVersion is not in Succeeded phase:\n"
                "  advanced-cluster-management.v2.12.0 - Phase: Failed, Reason: InstallFailed, Message: install failed"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but no pods found",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(return_value=[]),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg="No pods found in open-cluster-management namespace.",
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running"),
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "cluster-manager-xyz789", "Pending"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg=(
                "Unhealthy pods in open-cluster-management namespace:\n"
                "  cluster-manager-xyz789 - Phase: Pending"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Running", False),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg=(
                "Unhealthy pods in open-cluster-management namespace:\n"
                "  multiclusterhub-operator-abc123 - Running, Not all containers ready"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV failed and pods unhealthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(VerifyAcmOperatorHealth.ACM_NAMESPACE, "multiclusterhub-operator-abc123", "Pending"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response(phase="Failed"))),
            },
            failed_msg=(
                "ACM ClusterServiceVersion is not in Succeeded phase:\n"
                "  advanced-cluster-management.v2.12.0 - Phase: Failed, "
                "Reason: InstallFailed, Message: install failed\n\n"
                "Unhealthy pods in open-cluster-management namespace:\n"
                "  multiclusterhub-operator-abc123 - Phase: Pending"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when ACM operator subscription exists."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when ACM operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when ACM CSV is succeeded and all pods are healthy."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when ACM CSV or pods are unhealthy."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)



def _workload_availability_subscriptions(include_nmo=False, include_far=False, include_mdr=False):
    """Build a subscriptions response with optional workload availability operator subscriptions."""
    items = []
    if include_nmo:
        items.append(
            {
                "metadata": {"name": "nmo-sub", "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE},
                "spec": {"name": "node-maintenance-operator", "source": "redhat-operators"},
            }
        )
    if include_far:
        items.append(
            {
                "metadata": {"name": "far-sub", "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE},
                "spec": {"name": "fence-agents-remediation", "source": "redhat-operators"},
            }
        )
    if include_mdr:
        items.append(
            {
                "metadata": {"name": "mdr-sub", "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE},
                "spec": {"name": "machine-deletion-remediation-operator", "source": "redhat-operators"},
            }
        )
    items.append(
        {
            "metadata": {"name": "other-operator", "namespace": "openshift-operators"},
            "spec": {"name": "other", "source": "redhat-operators"},
        }
    )
    return {"items": items}


_WA_SUB_CMD = ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"))


class TestVerifyWorkloadAvailabilityNamespaceHealth(RuleTestBase):
    """Test VerifyWorkloadAvailabilityNamespaceHealth rule."""

    tested_type = VerifyWorkloadAvailabilityNamespaceHealth

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NMO subscription found",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_nmo=True))
                ),
            },
        ),
        RuleScenarioParams(
            "FAR subscription found",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_far=True))
                ),
            },
        ),
        RuleScenarioParams(
            "MDR subscription found",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_mdr=True))
                ),
            },
        ),
        RuleScenarioParams(
            "all three subscriptions found",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(
                        _workload_availability_subscriptions(
                            include_nmo=True, include_far=True, include_mdr=True
                        )
                    )
                ),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no workload availability operator subscriptions found",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions())
                ),
            },
        ),
        RuleScenarioParams(
            "no subscriptions exist in cluster",
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(json.dumps({"items": []})),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "all pods healthy in namespace",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "fence-agents-remediation-controller-manager-def456",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "mdr-controller-manager-ghi789",
                            "Running",
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_nmo=True))
                ),
            },
        ),
        RuleScenarioParams(
            "all three operators installed and all pods healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "fence-agents-remediation-controller-manager-def456",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "mdr-controller-manager-ghi789",
                            "Running",
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(
                        _workload_availability_subscriptions(
                            include_nmo=True, include_far=True, include_mdr=True
                        )
                    )
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "no pods found in namespace",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(return_value=[]),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_nmo=True))
                ),
            },
            failed_msg="No pods found in openshift-workload-availability namespace.",
        ),
        RuleScenarioParams(
            "some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "fence-agents-remediation-controller-manager-def456",
                            "Pending",
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_far=True))
                ),
            },
            failed_msg="Unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-controller-manager-def456 - Phase: Pending",
        ),
        RuleScenarioParams(
            "containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "mdr-controller-manager-abc123",
                            "Running",
                            False,
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_mdr=True))
                ),
            },
            failed_msg="Unhealthy pods in openshift-workload-availability namespace:\n"
            "  mdr-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "pod in unexpected succeeded state",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "node-maintenance-operator-controller-manager-abc123",
                            "Succeeded",
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_nmo=True))
                ),
            },
            failed_msg="Pods in unexpected succeeded state in openshift-workload-availability namespace:\n"
            "  node-maintenance-operator-controller-manager-abc123",
        ),
        RuleScenarioParams(
            "mixed succeeded and unhealthy pods",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "mdr-controller-manager-abc123",
                            "Succeeded",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "fence-agents-remediation-controller-manager-def456",
                            "Running",
                            False,
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(_workload_availability_subscriptions(include_far=True))
                ),
            },
            failed_msg="Pods in unexpected succeeded state in openshift-workload-availability namespace:\n"
            "  mdr-controller-manager-abc123\n\n"
            "Unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-controller-manager-def456 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "one operator pod unhealthy while sibling operator pods are healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "fence-agents-remediation-controller-manager-def456",
                            "CrashLoopBackOff",
                        ),
                        create_mock_pod(
                            VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                            "mdr-controller-manager-ghi789",
                            "Running",
                        ),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _WA_SUB_CMD: CmdOutput(
                    json.dumps(
                        _workload_availability_subscriptions(
                            include_nmo=True, include_far=True, include_mdr=True
                        )
                    )
                ),
            },
            failed_msg="Unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-controller-manager-def456 - Phase: CrashLoopBackOff",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


def _far_subscription_response(has_far=True):
    """Build OLM subscription list response."""
    items = []
    if has_far:
        items.append(
            {
                "metadata": {
                    "name": "fence-agents-remediation",
                    "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                },
                "spec": {"name": "fence-agents-remediation"},
            }
        )
    return {"items": items}


def _far_subscription_response_custom_name():
    """Build OLM subscription list with custom metadata.name but correct spec.name."""
    return {
        "items": [
            {
                "metadata": {
                    "name": "my-custom-far-sub",
                    "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE,
                },
                "spec": {"name": "fence-agents-remediation"},
            }
        ]
    }


def _create_far_pod(
    name,
    run_as_non_root=True,
    containers_run_as_user=None,
    has_security_context=True,
    has_run_as_non_root=True,
    has_containers=True,
    init_containers_run_as_user=None,
    containers_run_as_non_root=None,
):
    """Create a mock FAR pod object for security context tests.

    Args:
        name: Pod name
        run_as_non_root: Value for pod-level runAsNonRoot
        containers_run_as_user: List of runAsUser values per container (None means no securityContext)
        has_security_context: Whether pod has a securityContext at all
        has_run_as_non_root: Whether runAsNonRoot is present in securityContext
        has_containers: Whether the pod has containers
        init_containers_run_as_user: List of runAsUser values per init container (None means no initContainers)
        containers_run_as_non_root: List of runAsNonRoot values per container (must match containers_run_as_user length)
    """
    mock_pod = Mock()
    spec = {}

    if has_security_context:
        sc = {}
        if has_run_as_non_root:
            sc["runAsNonRoot"] = run_as_non_root
        spec["securityContext"] = sc
    else:
        spec["securityContext"] = None

    if has_containers:
        containers = []
        if containers_run_as_user is None:
            containers_run_as_user = [1000]
        for i, uid in enumerate(containers_run_as_user):
            container = {"name": f"container-{uid}"}
            if uid is not None:
                container["securityContext"] = {"runAsUser": uid}
            else:
                container["securityContext"] = None
            if containers_run_as_non_root is not None and container["securityContext"] is not None:
                container["securityContext"]["runAsNonRoot"] = containers_run_as_non_root[i]
            containers.append(container)
        spec["containers"] = containers
    else:
        spec["containers"] = []

    if init_containers_run_as_user is not None:
        init_containers = []
        for uid in init_containers_run_as_user:
            ic = {"name": f"init-container-{uid}"}
            if uid is not None:
                ic["securityContext"] = {"runAsUser": uid}
            else:
                ic["securityContext"] = None
            init_containers.append(ic)
        spec["initContainers"] = init_containers

    mock_pod.name.return_value = name
    mock_pod.as_dict.return_value = {
        "metadata": {"name": name, "namespace": VerifyWorkloadAvailabilityNamespaceHealth.WORKLOAD_AVAILABILITY_NAMESPACE},
        "spec": spec,
    }
    return mock_pod


class TestVerifyFarContainerNonRoot(RuleTestBase):
    """Test VerifyFarContainerNonRoot rule."""

    tested_type = VerifyFarContainerNonRoot

    scenario_passed = [
        RuleScenarioParams(
            "FAR pod runs as non-root with proper security context",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-controller-manager-abc123",
                            run_as_non_root=True,
                            containers_run_as_user=[1000],
                        ),
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "multiple FAR pods all run as non-root",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-controller-manager-abc123",
                            run_as_non_root=True,
                            containers_run_as_user=[1000],
                        ),
                        _create_far_pod(
                            "far-controller-manager-def456",
                            run_as_non_root=True,
                            containers_run_as_user=[1000, 65534],
                        ),
                    ]
                ),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "FAR operator subscription not found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=False))),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "FAR operator subscription exists",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
        ),
        RuleScenarioParams(
            "FAR subscription with custom metadata.name but correct spec.name",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response_custom_name())),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "no FAR pods found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(return_value=[]),
            },
            failed_msg="No FAR pods found with label app.kubernetes.io/name=fence-agents-remediation-operator",
        ),
        RuleScenarioParams(
            "FAR pod has nil SecurityContext",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod("far-pod-1", has_security_context=False),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n- Pod far-pod-1 has nil SecurityContext\n",
        ),
        RuleScenarioParams(
            "FAR pod has nil runAsNonRoot",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod("far-pod-1", has_run_as_non_root=False),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n- Pod far-pod-1 has nil runAsNonRoot\n",
        ),
        RuleScenarioParams(
            "FAR pod has runAsNonRoot set to false",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod("far-pod-1", run_as_non_root=False),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Incorrect runAsNonRoot for pod far-pod-1. Expected true, found: False\n",
        ),
        RuleScenarioParams(
            "FAR pod has no containers",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod("far-pod-1", has_containers=False),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n- Pod far-pod-1 has no containers\n",
        ),
        RuleScenarioParams(
            "FAR container runs as root (runAsUser=0)",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-pod-1",
                            run_as_non_root=True,
                            containers_run_as_user=[0],
                        ),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Container 'container-0' in pod far-pod-1 runs as root (runAsUser=0)\n",
        ),
        RuleScenarioParams(
            "FAR container overrides pod-level runAsNonRoot to false",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-pod-1",
                            run_as_non_root=True,
                            containers_run_as_user=[1000],
                            containers_run_as_non_root=[False],
                        ),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Container 'container-1000' in pod far-pod-1 has runAsNonRoot set to false\n",
        ),
        RuleScenarioParams(
            "FAR init container runs as root (runAsUser=0)",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-pod-1",
                            run_as_non_root=True,
                            containers_run_as_user=[1000],
                            init_containers_run_as_user=[0],
                        ),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Container 'init-container-0' in pod far-pod-1 runs as root (runAsUser=0)\n",
        ),
        RuleScenarioParams(
            "mixed failures - nil SecurityContext and root container",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod("far-pod-1", has_security_context=False),
                        _create_far_pod(
                            "far-pod-2",
                            run_as_non_root=True,
                            containers_run_as_user=[0, 1000],
                        ),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Pod far-pod-1 has nil SecurityContext\n"
            "- Container 'container-0' in pod far-pod-2 runs as root (runAsUser=0)\n",
        ),
        RuleScenarioParams(
            "FAR container has invalid runAsUser (negative value)",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscription_response(has_far=True))),
            },
            tested_object_mock_dict={
                "oc_api.get_pods": Mock(
                    return_value=[
                        _create_far_pod(
                            "far-pod-1",
                            run_as_non_root=True,
                            containers_run_as_user=[-1],
                        ),
                    ]
                ),
            },
            failed_msg="FAR operator pods doesn't have proper security context:\n"
            "- Container 'container--1' in pod far-pod-1 has invalid runAsUser: -1\n",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)



