"""
Tests for K8s/OpenShift validations.

Adapted from HealthChecks test patterns for AllPodsReadyAndRunning.
"""

import json
from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.k8s.subscription_operator_validations import (
    VerifyAcmOperatorHealth,
    VerifyFarContainerNonRoot,
    VerifyFarOperatorHealth,
    VerifyMdrOperatorHealth,
    VerifyNfdOperatorHealth,
    VerifyNfdPodRestartCount,
    VerifyNmoOperatorHealth,
)
from in_cluster_checks.utils.enums import Status
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def create_mock_nfd_pod(name, phase, all_containers_ready=True):
    """Create a mock NFD pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": "openshift-nfd", "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


def _nfd_subscriptions(include_nfd=True):
    """Build a subscriptions response, optionally including the nfd subscription."""
    items = []
    if include_nfd:
        items.append(
            {
                "metadata": {"name": "nfd-sub", "namespace": "openshift-nfd"},
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
                        create_mock_nfd_pod("nfd-controller-manager-abc123", "Running", True),
                        create_mock_nfd_pod("nfd-worker-xyz789", "Running", True),
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
            failed_msg="No pods found in openshift-nfd namespace. NFD operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "NFD operator installed but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nfd_pod("nfd-controller-manager-abc123", "Running", True),
                        create_mock_nfd_pod("nfd-worker-xyz789", "Pending", True),
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
            failed_msg="NFD operator has unhealthy pods in openshift-nfd namespace:\n"
            "  nfd-worker-xyz789 - Phase: Pending",
        ),
        RuleScenarioParams(
            "NFD operator installed but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nfd_pod("nfd-controller-manager-abc123", "Running", False),
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
            failed_msg="NFD operator has unhealthy pods in openshift-nfd namespace:\n"
            "  nfd-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "NFD operator installed but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nfd_pod("nfd-controller-manager-abc123", "Succeeded", True),
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
            failed_msg="Failed to evaluate status for NFD pod(s):\n  nfd-controller-manager-abc123",
        ),
    ]

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
        "metadata": {"name": name, "namespace": "openshift-nfd"},
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


def create_mock_acm_pod(name, phase, all_containers_ready=True):
    """Create a mock ACM pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": "open-cluster-management", "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


def _acm_subscriptions(include_acm=True, installed_csv="advanced-cluster-management.v2.12.0"):
    """Build a subscriptions response, optionally including the ACM subscription."""
    items = []
    if include_acm:
        sub = {
            "metadata": {"name": "acm-sub", "namespace": "open-cluster-management"},
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
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", True),
                        create_mock_acm_pod("cluster-manager-xyz789", "Running", True),
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
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True, installed_csv=None))),
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
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", True),
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
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", True),
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
            failed_msg="No pods found in open-cluster-management namespace. ACM operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", True),
                        create_mock_acm_pod("cluster-manager-xyz789", "Pending", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg=(
                "ACM operator has unhealthy pods in open-cluster-management namespace:\n"
                "  cluster-manager-xyz789 - Phase: Pending"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Running", False),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg=(
                "ACM operator has unhealthy pods in open-cluster-management namespace:\n"
                "  multiclusterhub-operator-abc123 - Running, Not all containers ready"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Succeeded", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg="Failed to evaluate status for ACM pod(s):\n  multiclusterhub-operator-abc123",
        ),
        RuleScenarioParams(
            "ACM CSV succeeded but mixed unknown and unhealthy pods",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_acm_pod("completed-job-pod", "Succeeded", True),
                        create_mock_acm_pod("cluster-manager-xyz789", "Pending", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                _ACM_SUB_CMD: CmdOutput(json.dumps(_acm_subscriptions(include_acm=True))),
                _ACM_CSV_CMD: CmdOutput(json.dumps(_acm_csv_response())),
            },
            failed_msg=(
                "Failed to evaluate status for ACM pod(s):\n"
                "  completed-job-pod\n\n"
                "ACM operator has unhealthy pods in open-cluster-management namespace:\n"
                "  cluster-manager-xyz789 - Phase: Pending"
            ),
        ),
        RuleScenarioParams(
            "ACM CSV failed and pods unhealthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_acm_pod("multiclusterhub-operator-abc123", "Pending", True),
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
                "ACM operator has unhealthy pods in open-cluster-management namespace:\n"
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


def create_mock_far_pod(name, phase, all_containers_ready=True):
    """Create a mock FAR pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": "openshift-workload-availability", "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


def _far_subscriptions(include_far=True):
    """Build a subscriptions response, optionally including the FAR subscription."""
    items = []
    if include_far:
        items.append(
            {
                "metadata": {
                    "name": "far-sub",
                    "namespace": "openshift-workload-availability",
                },
                "spec": {
                    "name": "fence-agents-remediation",
                    "source": "redhat-operators",
                },
            }
        )
    return {"items": items}


class TestVerifyFarOperatorHealth(RuleTestBase):
    """Tests for VerifyFarOperatorHealth rule."""

    tested_type = VerifyFarOperatorHealth

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "FAR operator subscription found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "FAR operator installed and all pods healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_far_pod(
                            "fence-agents-remediation-controller-manager-abc123",
                            "Running",
                            True,
                        ),
                        create_mock_far_pod("fence-agents-remediation-worker-xyz789", "Running", True),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=False))),
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
            "FAR operator installed but no pods found",
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
            failed_msg="No pods found in openshift-workload-availability namespace."
            " FAR operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "FAR operator installed but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_far_pod(
                            "fence-agents-remediation-controller-manager-abc123",
                            "Running",
                            True,
                        ),
                        create_mock_far_pod("fence-agents-remediation-worker-xyz789", "Pending", True),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
            failed_msg="FAR operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-worker-xyz789 - Phase: Pending",
        ),
        RuleScenarioParams(
            "FAR operator installed but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_far_pod(
                            "fence-agents-remediation-controller-manager-abc123",
                            "Running",
                            False,
                        ),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
            failed_msg="FAR operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "FAR operator installed but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_far_pod(
                            "fence-agents-remediation-controller-manager-abc123",
                            "Succeeded",
                            True,
                        ),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
            failed_msg="Failed to evaluate status for FAR pod(s):\n"
            "  fence-agents-remediation-controller-manager-abc123",
        ),
        RuleScenarioParams(
            "FAR operator installed with unknown and unhealthy pods",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_far_pod(
                            "fence-agents-remediation-controller-manager-abc123",
                            "Succeeded",
                            True,
                        ),
                        create_mock_far_pod("fence-agents-remediation-worker-xyz789", "Running", False),
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
                ): CmdOutput(json.dumps(_far_subscriptions(include_far=True))),
            },
            failed_msg="Failed to evaluate status for FAR pod(s):\n"
            "  fence-agents-remediation-controller-manager-abc123\n\n"
            "FAR operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  fence-agents-remediation-worker-xyz789 - Running, Not all containers ready",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when FAR operator is installed."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when FAR operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when all FAR pods are healthy."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when FAR pods are unhealthy or missing."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


def _far_subscription_response(has_far=True):
    """Build OLM subscription list response."""
    items = []
    if has_far:
        items.append(
            {
                "metadata": {
                    "name": "fence-agents-remediation",
                    "namespace": "openshift-workload-availability",
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
                    "namespace": "openshift-workload-availability",
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
        for uid in containers_run_as_user:
            container = {"name": f"container-{uid}"}
            if uid is not None:
                container["securityContext"] = {"runAsUser": uid}
            else:
                container["securityContext"] = None
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
        "metadata": {"name": name, "namespace": "openshift-workload-availability"},
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


def create_mock_nmo_pod(name, phase, all_containers_ready=True):
    """Create a mock NMO pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": "openshift-workload-availability", "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


def _nmo_subscriptions(include_nmo=True):
    """Build a subscriptions response, optionally including the NMO subscription."""
    items = []
    if include_nmo:
        items.append(
            {
                "metadata": {
                    "name": "nmo-sub",
                    "namespace": "openshift-workload-availability",
                },
                "spec": {
                    "name": "node-maintenance-operator",
                    "source": "redhat-operators",
                },
            }
        )
    return {"items": items}


class TestVerifyNmoOperatorHealth(RuleTestBase):
    """Tests for VerifyNmoOperatorHealth rule."""

    tested_type = VerifyNmoOperatorHealth

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NMO operator subscription found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "NMO operator installed and all pods healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nmo_pod(
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                            True,
                        ),
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "NMO operator subscription not found",
            oc_cmd_output_dict={
                (
                    "get",
                    (
                        "subscriptions.operators.coreos.com",
                        "--all-namespaces",
                        "-o",
                        "json",
                    ),
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=False))),
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
            "NMO operator installed but no pods found",
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
            failed_msg="No pods found in openshift-workload-availability namespace."
            " NMO operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "NMO operator installed but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nmo_pod(
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                            True,
                        ),
                        create_mock_nmo_pod("node-maintenance-operator-worker-xyz789", "Pending", True),
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
            failed_msg="NMO operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  node-maintenance-operator-worker-xyz789 - Phase: Pending",
        ),
        RuleScenarioParams(
            "NMO operator installed but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nmo_pod(
                            "node-maintenance-operator-controller-manager-abc123",
                            "Running",
                            False,
                        ),
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
            failed_msg="NMO operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  node-maintenance-operator-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "NMO operator installed but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nmo_pod(
                            "node-maintenance-operator-controller-manager-abc123",
                            "Succeeded",
                            True,
                        ),
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
            failed_msg="Failed to evaluate status for NMO pod(s):\n"
            "  node-maintenance-operator-controller-manager-abc123",
        ),
        RuleScenarioParams(
            "NMO operator installed with unknown and unhealthy pods",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_nmo_pod(
                            "node-maintenance-operator-controller-manager-abc123",
                            "Succeeded",
                            True,
                        ),
                        create_mock_nmo_pod("node-maintenance-operator-worker-xyz789", "Running", False),
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
                ): CmdOutput(json.dumps(_nmo_subscriptions(include_nmo=True))),
            },
            failed_msg="Failed to evaluate status for NMO pod(s):\n"
            "  node-maintenance-operator-controller-manager-abc123\n\n"
            "NMO operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  node-maintenance-operator-worker-xyz789 - Running, Not all containers ready",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when NMO operator is installed."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when NMO operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when all NMO pods are healthy."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when NMO pods are unhealthy or missing."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

def create_mock_mdr_pod(name, phase, all_containers_ready=True):
    """Create a mock MDR pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": "openshift-workload-availability", "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


def _mdr_subscriptions(include_mdr=True):
    """Build a subscriptions response, optionally including the MDR subscription."""
    items = []
    if include_mdr:
        items.append(
            {
                "metadata": {"name": "mdr-sub", "namespace": "openshift-workload-availability"},
                "spec": {"name": "openshift-workload-availability", "source": "redhat-operators"},
            }
        )
    items.append(
        {
            "metadata": {"name": "other-operator", "namespace": "openshift-operators"},
            "spec": {"name": "other", "source": "redhat-operators"},
        }
    )
    return {"items": items}


class TestVerifyMdrOperatorHealth(RuleTestBase):
    """Test VerifyMdrOperatorHealth rule."""

    tested_type = VerifyMdrOperatorHealth

    scenario_passed = [
        RuleScenarioParams(
            "MDR operator installed and all pods are healthy",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_mdr_pod("mdr-controller-manager-abc123", "Running", True),
                        create_mock_mdr_pod("mdr-worker-xyz789", "Running", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=True))
                ),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "MDR operator subscription not found",
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=False))
                ),
            },
        ),
        RuleScenarioParams(
            "no subscriptions exist in cluster",
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps({"items": []})
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "MDR operator installed but no pods found",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(return_value=[]),
            },
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=True))
                ),
            },
            failed_msg="No pods found in openshift-workload-availability namespace. "
            "Machine Deletion Remediation operator may not be fully deployed.",
        ),
        RuleScenarioParams(
            "MDR operator installed but some pods are not running",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_mdr_pod("mdr-controller-manager-abc123", "Running", True),
                        create_mock_mdr_pod("mdr-worker-xyz789", "Pending", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=True))
                ),
            },
            failed_msg="Machine Deletion Remediation operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  mdr-worker-xyz789 - Phase: Pending",
        ),
        RuleScenarioParams(
            "MDR operator installed but containers not ready",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_mdr_pod("mdr-controller-manager-abc123", "Running", False),
                    ]
                ),
            },
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=True))
                ),
            },
            failed_msg="Machine Deletion Remediation operator has unhealthy pods in openshift-workload-availability namespace:\n"
            "  mdr-controller-manager-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "MDR operator installed but pod status unknown",
            tested_object_mock_dict={
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_mdr_pod("mdr-controller-manager-abc123", "Succeeded", True),
                    ]
                ),
            },
            oc_cmd_output_dict={
                ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json")): CmdOutput(
                    json.dumps(_mdr_subscriptions(include_mdr=True))
                ),
            },
            failed_msg="Machine Deletion Remediation operator has pods in unexpected succeeded state:\n  mdr-controller-manager-abc123",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when MDR operator is not installed."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that rule passes when all MDR pods are healthy."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that rule fails when MDR pods are unhealthy or missing."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
