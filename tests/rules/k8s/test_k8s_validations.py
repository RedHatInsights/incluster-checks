"""
Tests for K8s/OpenShift validations.

Adapted from HealthChecks test patterns for AllPodsReadyAndRunning.
"""

import json

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.k8s.k8s_validations import (
    AllDeploymentsAvailable,
    AllPodsReadyAndRunning,
    AllStatefulsetsReady,
    CheckDeploymentsReplicaStatus,
    NodesAreReady,
    NodesCpuAndMemoryStatus,
    OpenshiftOperatorStatus,
    ValidateAllDaemonsetsScheduled,
    ValidateAllPoliciesCompliant,
    ValidateNamespaceStatus,
    VerifyInternalRegistry,
)
from in_cluster_checks.utils.enums import Status
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def create_mock_pod(namespace, name, phase, ready_containers, total_containers):
    """Create a mock pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": i < ready_containers} for i in range(total_containers)
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": namespace, "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


class TestAllPodsReadyAndRunning:
    """Test AllPodsReadyAndRunning rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of AllPodsReadyAndRunning for testing."""
        return AllPodsReadyAndRunning(host_executor=Mock(), node_executors={})

    def test_all_pods_running_and_ready(self, tested_object):
        """Test when all pods are running and ready."""
        tested_object.oc_api.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "pod1", "Running", 2, 2),
                create_mock_pod("kube-system", "pod2", "Running", 1, 1),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_pods_not_running(self, tested_object):
        """Test when some pods are not in Running state."""
        tested_object.oc_api.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "running-pod", "Running", 1, 1),
                create_mock_pod("default", "pending-pod", "Pending", 0, 1),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "pending-pod" in result.message
        assert "Pending" in result.message

    def test_completed_pods_ignored(self, tested_object):
        """Test that completed/succeeded pods are ignored."""
        tested_object.oc_api.get_all_pods = Mock(
            return_value=[
                create_mock_pod("default", "running-pod", "Running", 1, 1),
                create_mock_pod("default", "completed-job", "Succeeded", 0, 1),
            ]
        )

        result = tested_object.run_rule()
        # Should pass because completed jobs are ignored
        assert result.status == Status.PASSED

    def test_no_pods_found(self, tested_object):
        """Test when no pods are found in the cluster."""
        tested_object.oc_api.get_all_pods = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "Did not get any pods" in result.message


def create_mock_node(name, ready_status, other_conditions=None):
    """Create a mock node object."""
    mock_node = Mock()
    conditions = [{"type": "Ready", "status": ready_status}]

    if other_conditions:
        conditions.extend(other_conditions)

    mock_node.as_dict.return_value = {
        "metadata": {"name": name},
        "status": {"conditions": conditions},
    }
    return mock_node


class TestNodesAreReady:
    """Test NodesAreReady rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of NodesAreReady for testing."""
        return NodesAreReady(host_executor=Mock(), node_executors={})

    def test_all_nodes_ready(self, tested_object):
        """Test when all nodes are ready."""
        tested_object.oc_api.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node("node2", "True"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_nodes_not_ready(self, tested_object):
        """Test when some nodes are not ready."""
        tested_object.oc_api.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node("node2", "False"),
                create_mock_node("node3", "Unknown"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node2" in result.message
        assert "node3" in result.message
        assert "not ready" in result.message

    def test_nodes_with_warnings(self, tested_object):
        """Test when nodes have warning conditions."""
        tested_object.oc_api.get_all_nodes = Mock(
            return_value=[
                create_mock_node("node1", "True"),
                create_mock_node(
                    "node2",
                    "True",
                    [{"type": "DiskPressure", "status": "True"}],
                ),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node2" in result.message
        assert "DiskPressure" in result.message

    def test_no_nodes_found(self, tested_object):
        """Test when no nodes are found."""
        tested_object.oc_api.get_all_nodes = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "Did not get nodes list" in result.message


class TestNodesCpuAndMemoryStatus:
    """Test NodesCpuAndMemoryStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of NodesCpuAndMemoryStatus for testing."""
        return NodesCpuAndMemoryStatus(host_executor=Mock(), node_executors={})

    def test_all_nodes_normal_usage(self, tested_object):
        """Test when all nodes have normal CPU/memory usage."""
        tested_object.oc_api.run_oc_command = Mock(
            return_value=(0, "node1    100m    5%     2000Mi   10%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_high_cpu_usage(self, tested_object):
        """Test when some nodes have high CPU usage."""
        tested_object.oc_api.run_oc_command = Mock(
            return_value=(0, "node1    10000m  85%    2000Mi   10%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node1" in result.message
        assert "85%" in result.message
        assert "high CPU usage" in result.message

    def test_high_memory_usage(self, tested_object):
        """Test when some nodes have high memory usage."""
        tested_object.oc_api.run_oc_command = Mock(
            return_value=(0, "node1    100m    5%     50000Mi  90%\nnode2    200m    10%    3000Mi   15%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "node1" in result.message
        assert "90%" in result.message
        assert "high memory usage" in result.message

    def test_critical_threshold_exceeded(self, tested_object):
        """Test when critical threshold is exceeded."""
        tested_object.oc_api.run_oc_command = Mock(
            return_value=(0, "node1    10000m  95%    2000Mi   10%", "")
        )

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "CRITICAL" in result.message
        assert "95%" in result.message

    def test_no_metrics_available(self, tested_object):
        """Test when no metrics are available."""
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, "", ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No node metrics available" in result.message


def create_mock_namespace(name, phase):
    """Create a mock namespace object."""
    mock_ns = Mock()
    mock_ns.as_dict.return_value = {
        "metadata": {"name": name},
        "status": {"phase": phase},
    }
    return mock_ns


def create_mock_deployment(name, namespace, spec=None, status=None):
    """Create a mock deployment object.

    Args:
        name: Deployment name
        namespace: Namespace name
        spec: Dict with spec fields (e.g., {"replicas": 3})
        status: Dict with status fields (e.g., {"conditions": [...], "readyReplicas": 3})
    """
    mock_deployment = Mock()
    deployment_dict = {
        "metadata": {"name": name, "namespace": namespace},
    }

    if spec:
        deployment_dict["spec"] = spec
    if status:
        deployment_dict["status"] = status

    mock_deployment.as_dict.return_value = deployment_dict
    return mock_deployment


def create_mock_statefulset(name, namespace, spec=None, status=None):
    """Create a mock statefulset object.

    Args:
        name: StatefulSet name
        namespace: Namespace name
        spec: Dict with spec fields (e.g., {"replicas": 3})
        status: Dict with status fields (e.g., {"readyReplicas": 3})
    """
    mock_statefulset = Mock()
    statefulset_dict = {
        "metadata": {"name": name, "namespace": namespace},
    }

    if spec:
        statefulset_dict["spec"] = spec
    if status:
        statefulset_dict["status"] = status

    mock_statefulset.as_dict.return_value = statefulset_dict
    return mock_statefulset


class TestValidateNamespaceStatus:
    """Test ValidateNamespaceStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of ValidateNamespaceStatus for testing."""
        return ValidateNamespaceStatus(host_executor=Mock(), node_executors={})

    def test_all_namespaces_active(self, tested_object):
        """Test when all namespaces are active."""
        tested_object.oc_api.get_all_namespaces = Mock(
            return_value=[
                create_mock_namespace("default", "Active"),
                create_mock_namespace("kube-system", "Active"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_namespaces_terminating(self, tested_object):
        """Test when some namespaces are terminating."""
        tested_object.oc_api.get_all_namespaces = Mock(
            return_value=[
                create_mock_namespace("default", "Active"),
                create_mock_namespace("old-ns", "Terminating"),
            ]
        )

        result = tested_object.run_rule()
        assert result.status == Status.WARNING
        assert "old-ns" in result.message
        assert "Terminating" in result.message

    def test_no_namespaces_found(self, tested_object):
        """Test when no namespaces are found."""
        tested_object.oc_api.get_all_namespaces = Mock(return_value=[])

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No namespaces found" in result.message


class TestValidateAllDaemonsetsScheduled:
    """Test ValidateAllDaemonsetsScheduled rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of ValidateAllDaemonsetsScheduled for testing."""
        return ValidateAllDaemonsetsScheduled(host_executor=Mock(), node_executors={})

    def test_all_daemonsets_scheduled(self, tested_object):
        """Test when all daemonsets have desired number of pods and none unavailable."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 3,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_some_daemonsets_not_fully_scheduled(self, tested_object):
        """Test when some daemonsets don't have desired number of pods."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "ds1" in result.message
        assert "kube-system" in result.message
        assert "Desired: 3" in result.message
        assert "Current: 2" in result.message
        assert "pods not being scheduled" in result.message

    def test_daemonset_with_zero_desired_is_skipped(self, tested_object):
        """Test that daemonsets with 0 desired pods are skipped (no matching nodes)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "vg-manager", "namespace": "openshift-storage"},
                    "status": {
                        "desiredNumberScheduled": 0,
                        "currentNumberScheduled": 0,
                        "numberUnavailable": 0,
                    },
                },
                {
                    "metadata": {"name": "ds2", "namespace": "default"},
                    "status": {
                        "desiredNumberScheduled": 2,
                        "currentNumberScheduled": 2,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_daemonset_pods_initializing_passes(self, tested_object):
        """Test that daemonsets with pods still initializing pass (not explicitly unavailable)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "vg-manager", "namespace": "openshift-storage"},
                    "status": {
                        "desiredNumberScheduled": 1,
                        "currentNumberScheduled": 1,
                        "numberUnavailable": 0,
                    },
                },
            ]
        }
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.PASSED

    def test_daemonset_with_unavailable_pods(self, tested_object):
        """Test when daemonset has pods marked as unavailable (real issue)."""
        daemonsets_data = {
            "items": [
                {
                    "metadata": {"name": "ds1", "namespace": "kube-system"},
                    "status": {
                        "desiredNumberScheduled": 3,
                        "currentNumberScheduled": 3,
                        "numberUnavailable": 2,
                    },
                },
            ]
        }
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, json.dumps(daemonsets_data), ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "ds1" in result.message
        assert "kube-system" in result.message
        assert "2 pod(s) unavailable" in result.message


class TestOpenshiftOperatorStatus:
    """Test OpenshiftOperatorStatus rule."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of OpenshiftOperatorStatus for testing."""
        return OpenshiftOperatorStatus(host_executor=Mock(), node_executors={})

    def test_all_operators_available(self, tested_object):
        """Test when all operators are available and not progressing."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    True        False         False      14d
cloud-controller-manager                   4.15.29    True        False         False      14d
cluster-autoscaler                         4.15.29    True        False         False      14d"""

        tested_object.oc_api.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.INFO
        assert result.table_headers is not None
        assert result.table_data is not None
        assert result.table_headers == [
            "Name",
            "Version",
            "Available",
            "Progressing",
            "Degraded",
            "Since",
            "Message",
        ]
        assert len(result.table_data) == 4
        assert "All operators are available and stable" in result.message

    def test_some_operators_unavailable(self, tested_object):
        """Test when some operators are unavailable (Available=False)."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    False       False         False      14d     Operator is degraded
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.oc_api.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "baremetal" in result.message
        assert "not available" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_some_operators_progressing(self, tested_object):
        """Test when some operators are progressing (Progressing=True)."""
        operator_output = """authentication                             4.15.29    True        False         False      14d
baremetal                                  4.15.29    True        True          False      14d     Rolling out new pods
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.oc_api.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "baremetal" in result.message
        assert "in progress" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_operators_unavailable_and_progressing(self, tested_object):
        """Test when some operators are both unavailable and others progressing."""
        operator_output = """authentication                             4.15.29    False       False         False      14d     Auth issues
baremetal                                  4.15.29    True        True          False      14d     Rolling out
cloud-controller-manager                   4.15.29    True        False         False      14d"""

        tested_object.oc_api.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "authentication" in result.message
        assert "baremetal" in result.message
        assert "not available" in result.message
        assert "in progress" in result.message
        assert result.table_headers is not None
        assert result.table_data is not None

    def test_no_operators_found(self, tested_object):
        """Test when no cluster operators are found."""
        tested_object.oc_api.run_oc_command = Mock(return_value=(0, "", ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert "No cluster operators found" in result.message

    def test_table_sorting(self, tested_object):
        """Test that operators are sorted with problematic ones first."""
        operator_output = """good-operator                              4.15.29    True        False         False      14d
bad-operator                               4.15.29    False       False         False      14d     Problem
progressing-operator                       4.15.29    True        True          False      14d     Working
another-good-operator                      4.15.29    True        False         False      14d"""

        tested_object.oc_api.run_oc_command = Mock(return_value=(0, operator_output, ""))

        result = tested_object.run_rule()
        assert result.status == Status.FAILED

        # Check that table is sorted: Available=False first, then Progressing=True
        assert result.table_data is not None
        assert len(result.table_data) == 4

        # bad-operator (Available=False) should be first
        assert result.table_data[0][0] == "bad-operator"
        assert result.table_data[0][2] == "False"

        # progressing-operator (Progressing=True) should be second
        assert result.table_data[1][0] == "progressing-operator"
        assert result.table_data[1][3] == "True"


class TestAllDeploymentsAvailable(RuleTestBase):
    """Test AllDeploymentsAvailable rule."""

    tested_type = AllDeploymentsAvailable

    scenario_passed = [
        RuleScenarioParams(
            "all deployments are available",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment1",
                            "default",
                            status={
                                "conditions": [
                                    {"type": "Available", "status": "True"},
                                    {"type": "Progressing", "status": "False"},
                                ]
                            },
                        ),
                        create_mock_deployment(
                            "deployment2",
                            "kube-system",
                            status={
                                "conditions": [
                                    {"type": "Available", "status": "True"},
                                    {"type": "Progressing", "status": "False"},
                                ]
                            },
                        ),
                    ]
                )
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some deployments are not available",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment1",
                            "default",
                            status={
                                "conditions": [
                                    {"type": "Available", "status": "True"},
                                ]
                            },
                        ),
                        create_mock_deployment(
                            "deployment2",
                            "kube-system",
                            status={
                                "conditions": [
                                    {
                                        "type": "Available",
                                        "status": "False",
                                        "reason": "MinimumReplicasUnavailable",
                                        "message": "Deployment does not have minimum availability.",
                                    },
                                ]
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments are not available:\n"
            "  kube-system/deployment2 - Status: False, Reason: MinimumReplicasUnavailable, "
            "Message: Deployment does not have minimum availability.",
        ),
        RuleScenarioParams(
            "deployment has no Available condition",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment1",
                            "default",
                            status={
                                "conditions": [
                                    {"type": "Progressing", "status": "True"},
                                ]
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments are not available:\n"
            "  default/deployment1 - No Available condition found",
        ),
        RuleScenarioParams(
            "no deployments found in cluster",
            tested_object_mock_dict={"oc_api.get_all_deployments": Mock(return_value=[])},
            failed_msg="No deployments found in cluster",
        ),
        RuleScenarioParams(
            "deployments are in mixed states",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "good-deployment",
                            "default",
                            status={
                                "conditions": [
                                    {"type": "Available", "status": "True"},
                                ]
                            },
                        ),
                        create_mock_deployment(
                            "bad-deployment",
                            "app-ns",
                            status={
                                "conditions": [
                                    {
                                        "type": "Available",
                                        "status": "False",
                                        "reason": "DeploymentFailure",
                                        "message": "Pod failures",
                                    },
                                ]
                            },
                        ),
                        create_mock_deployment(
                            "no-condition-deployment",
                            "test-ns",
                            status={"conditions": []},
                        ),
                    ]
                )
            },
            failed_msg="Following deployments are not available:\n"
            "  app-ns/bad-deployment - Status: False, Reason: DeploymentFailure, Message: Pod failures\n"
            "  test-ns/no-condition-deployment - No Available condition found",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestCheckDeploymentsReplicaStatus(RuleTestBase):
    """Test CheckDeploymentsReplicaStatus rule."""

    tested_type = CheckDeploymentsReplicaStatus

    scenario_passed = [
        RuleScenarioParams(
            "all deployments have correct replica counts",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment1",
                            "default",
                            spec={"replicas": 3},
                            status={
                                "replicas": 3,
                                "readyReplicas": 3,
                                "availableReplicas": 3,
                                "updatedReplicas": 3,
                            },
                        ),
                        create_mock_deployment(
                            "deployment2",
                            "kube-system",
                            spec={"replicas": 1},
                            status={
                                "replicas": 1,
                                "readyReplicas": 1,
                                "availableReplicas": 1,
                                "updatedReplicas": 1,
                            },
                        ),
                    ]
                )
            },
        ),
        RuleScenarioParams(
            "deployment with zero replicas (scaled down) passes",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "scaled-down",
                            "default",
                            spec={"replicas": 0},
                            status={
                                "replicas": 0,
                                "readyReplicas": 0,
                                "availableReplicas": 0,
                                "updatedReplicas": 0,
                            },
                        ),
                        create_mock_deployment(
                            "normal-deployment",
                            "default",
                            spec={"replicas": 2},
                            status={
                                "replicas": 2,
                                "readyReplicas": 2,
                                "availableReplicas": 2,
                                "updatedReplicas": 2,
                            },
                        ),
                    ]
                )
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some deployments don't have all replicas ready",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment1",
                            "default",
                            spec={"replicas": 3},
                            status={
                                "replicas": 3,
                                "readyReplicas": 2,
                                "availableReplicas": 2,
                                "updatedReplicas": 3,
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments have replica count issues:\n"
            "  default/deployment1 - Desired: 3, Ready: 2",
        ),
        RuleScenarioParams(
            "some deployments don't have all replicas available",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment2",
                            "app-ns",
                            spec={"replicas": 5},
                            status={
                                "replicas": 5,
                                "readyReplicas": 5,
                                "availableReplicas": 4,
                                "updatedReplicas": 5,
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments have replica count issues:\n"
            "  app-ns/deployment2 - Desired: 5, Available: 4",
        ),
        RuleScenarioParams(
            "deployment has rollout in progress",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "deployment3",
                            "prod",
                            spec={"replicas": 3},
                            status={
                                "replicas": 3,
                                "readyReplicas": 3,
                                "availableReplicas": 3,
                                "updatedReplicas": 2,
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments have replica count issues:\n"
            "  prod/deployment3 - Desired: 3, Updated: 2 (rollout in progress)",
        ),
        RuleScenarioParams(
            "multiple deployments with different issues",
            tested_object_mock_dict={
                "oc_api.get_all_deployments": Mock(
                    return_value=[
                        create_mock_deployment(
                            "good-deployment",
                            "default",
                            spec={"replicas": 2},
                            status={
                                "replicas": 2,
                                "readyReplicas": 2,
                                "availableReplicas": 2,
                                "updatedReplicas": 2,
                            },
                        ),
                        create_mock_deployment(
                            "not-ready-deployment",
                            "app1",
                            spec={"replicas": 3},
                            status={
                                "replicas": 3,
                                "readyReplicas": 1,
                                "availableReplicas": 1,
                                "updatedReplicas": 3,
                            },
                        ),
                        create_mock_deployment(
                            "updating-deployment",
                            "app2",
                            spec={"replicas": 4},
                            status={
                                "replicas": 4,
                                "readyReplicas": 4,
                                "availableReplicas": 4,
                                "updatedReplicas": 2,
                            },
                        ),
                    ]
                )
            },
            failed_msg="Following deployments have replica count issues:\n"
            "  app1/not-ready-deployment - Desired: 3, Ready: 1\n"
            "  app2/updating-deployment - Desired: 4, Updated: 2 (rollout in progress)",
        ),
        RuleScenarioParams(
            "no deployments found in cluster",
            tested_object_mock_dict={"oc_api.get_all_deployments": Mock(return_value=[])},
            failed_msg="No deployments found in cluster",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestAllStatefulsetsReady(RuleTestBase):
    """Test AllStatefulsetsReady rule."""

    tested_type = AllStatefulsetsReady

    scenario_passed = [
        RuleScenarioParams(
            "all statefulsets are ready",
            tested_object_mock_dict={
                "oc_api.get_all_statefulsets": Mock(
                    return_value=[
                        create_mock_statefulset(
                            "statefulset1",
                            "default",
                            spec={"replicas": 3},
                            status={"readyReplicas": 3},
                        ),
                        create_mock_statefulset(
                            "statefulset2",
                            "kube-system",
                            spec={"replicas": 2},
                            status={"readyReplicas": 2},
                        ),
                    ]
                )
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some statefulsets are not ready",
            tested_object_mock_dict={
                "oc_api.get_all_statefulsets": Mock(
                    return_value=[
                        create_mock_statefulset(
                            "statefulset1",
                            "default",
                            spec={"replicas": 3},
                            status={"readyReplicas": 3},
                        ),
                        create_mock_statefulset(
                            "statefulset2",
                            "kube-system",
                            spec={"replicas": 3},
                            status={"readyReplicas": 1},
                        ),
                    ]
                )
            },
            failed_msg="Following statefulsets are not ready:\n"
            "  kube-system/statefulset2 - Desired: 3, Ready: 1",
        ),
        RuleScenarioParams(
            "statefulset has zero ready replicas",
            tested_object_mock_dict={
                "oc_api.get_all_statefulsets": Mock(
                    return_value=[
                        create_mock_statefulset(
                            "statefulset1",
                            "default",
                            spec={"replicas": 3},
                            status={"readyReplicas": 0},
                        ),
                    ]
                )
            },
            failed_msg="Following statefulsets are not ready:\n"
            "  default/statefulset1 - Desired: 3, Ready: 0",
        ),        
        RuleScenarioParams(
            "statefulsets in mixed states",
            tested_object_mock_dict={
                "oc_api.get_all_statefulsets": Mock(
                    return_value=[
                        create_mock_statefulset(
                            "good-statefulset",
                            "default",
                            spec={"replicas": 2},
                            status={"readyReplicas": 2},
                        ),
                        create_mock_statefulset(
                            "bad-statefulset",
                            "app-ns",
                            spec={"replicas": 5},
                            status={"readyReplicas": 2},
                        ),
                        create_mock_statefulset(
                            "another-bad-statefulset",
                            "test-ns",
                            spec={"replicas": 3},
                            status={"readyReplicas": 0},
                        ),
                    ]
                )
            },
            failed_msg="Following statefulsets are not ready:\n"
            "  app-ns/bad-statefulset - Desired: 5, Ready: 2\n"
            "  test-ns/another-bad-statefulset - Desired: 3, Ready: 0",
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "no statefulsets found in cluster",
            tested_object_mock_dict={"oc_api.get_all_statefulsets": Mock(return_value=[])},
            failed_msg="No statefulsets found in cluster",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)


class TestValidateAllPoliciesCompliant(RuleTestBase):
    """Test ValidateAllPoliciesCompliant rule."""

    tested_type = ValidateAllPoliciesCompliant

    # Sample policy data - all compliant
    all_compliant_policies = {
        "items": [
            {
                "metadata": {"name": "policy1", "namespace": "open-cluster-management"},
                "status": {"compliant": "Compliant"},
            },
            {
                "metadata": {"name": "policy2", "namespace": "open-cluster-management"},
                "status": {"compliant": "Compliant"},
            },
        ]
    }

    # Sample policy data - some non-compliant
    some_non_compliant_policies = {
        "items": [
            {
                "metadata": {"name": "policy1", "namespace": "open-cluster-management"},
                "status": {"compliant": "Compliant"},
            },
            {
                "metadata": {"name": "policy2", "namespace": "open-cluster-management"},
                "status": {"compliant": "NonCompliant"},
            },
            {
                "metadata": {"name": "policy3", "namespace": "policies"},
                "status": {"compliant": "Pending"},
            },
        ]
    }

    # No policies found
    no_policies = {"items": []}

    # Scenario where all policies are compliant
    scenario_passed = [
        RuleScenarioParams(
            "all policies are compliant",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(all_compliant_policies), ""))
            },
        ),
    ]
    # Scenario where some policies are non-compliant
    scenario_failed = [
        RuleScenarioParams(
            "some policies are non-compliant",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(some_non_compliant_policies), ""))
            },
            failed_msg="There are 2 non-compliant policies:\n"
            "  open-cluster-management/policy2 - NonCompliant\n"
            "  policies/policy3 - Pending",
        ),
    ]

    # Scenario where no policies are found
    scenario_warning = [
        RuleScenarioParams(
            "no policies found in cluster",
            tested_object_mock_dict={"oc_api.run_oc_command": Mock(return_value=(0, json.dumps(no_policies), ""))},
            failed_msg="No policies found in cluster",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)


def create_mock_registry_pod(name, namespace, phase, all_containers_ready=True):
    """Create a mock registry pod object."""
    mock_pod = Mock()
    container_statuses = [
        {"ready": all_containers_ready},
        {"ready": all_containers_ready},
    ]
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": namespace, "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": container_statuses,
        },
    }
    return mock_pod


class TestVerifyInternalRegistry(RuleTestBase):
    """Test VerifyInternalRegistry rule."""

    tested_type = VerifyInternalRegistry

    # Registry config - Managed state
    registry_config_managed = {
        "spec": {
            "managementState": "Managed",
            "storage": {"emptyDir": {}},
        },
        "status": {},
    }

    # Registry config - Removed state
    registry_config_removed = {
        "spec": {
            "managementState": "Removed",
        },
        "status": {},
    }

    # Registry config - Unmanaged state
    registry_config_unmanaged = {
        "spec": {
            "managementState": "Unmanaged",
        },
        "status": {},
    }

    scenario_passed = [
        RuleScenarioParams(
            "registry is managed and pods are running",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_managed), "")),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_registry_pod("image-registry-1", "openshift-image-registry", "Running", True),
                        create_mock_registry_pod("image-registry-2", "openshift-image-registry", "Running", True),
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "registry is managed with one running pod",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_managed), "")),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_registry_pod("image-registry-1", "openshift-image-registry", "Running", True),
                    ]
                ),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "registry is not in Managed state (Removed)",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_removed), "")),
            },
        ),
        RuleScenarioParams(
            "registry is not in Managed state (Unmanaged)",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_unmanaged), "")),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "registry is managed but no pods found",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_managed), "")),
                "oc_api.get_all_pods": Mock(return_value=[]),
            },
            failed_msg="Image registry is Managed but no registry pods found in openshift-image-registry namespace.\n",            
        ),
        RuleScenarioParams(
            "registry is managed but pods are not running",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_managed), "")),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_registry_pod("image-registry-1", "openshift-image-registry", "Pending", True),
                    ]
                ),
            },
            failed_msg="Image registry is Managed but following pods are not ready:\n"
            "  image-registry-1 - Phase: Pending",
        ),
        RuleScenarioParams(
            "registry is managed but pods running with containers not ready",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, json.dumps(registry_config_managed), "")),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_registry_pod("image-registry-1", "openshift-image-registry", "Running", False),
                    ]
                ),
            },
            failed_msg="Image registry is Managed but following pods are not ready:\n"
            "  image-registry-1 - Running, Not all containers ready",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
