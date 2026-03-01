"""
Unit tests for OVN-Kubernetes sanity check validations.

Tests for NodesHaveOvnkubeNodePod and LogicalSwitchNodeValidator.
Ported from: support/HealthChecks/tests/pytest/flows/network/test_ovnk8s_sanity_checks.py
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.network.ovnk8s_validations import (
    LogicalSwitchNodeValidator,
    NodesHaveOvnkubeNodePod,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


class OVNKubernetesTestBase(RuleTestBase):
    """Base class for OVN-Kubernetes validator tests."""

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled",
            tested_object_mock_dict={
                "is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))
            },
        )
    ]

    # Helper to create mock network object
    def _create_mock_network_ovnkube():
        mock_network = Mock()
        mock_network.model.spec.defaultNetwork.type = "OVNKubernetes"
        return mock_network

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={
                "_select_resources": Mock(return_value=_create_mock_network_ovnkube())
            },
        )
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)


class TestNodesHaveOvnkubeNodePod(OVNKubernetesTestBase):
    """Tests for NodesHaveOvnkubeNodePod validator."""

    tested_type = NodesHaveOvnkubeNodePod

    # Helper to create mock nodes
    def _create_mock_nodes():
        mock_node_1 = Mock()
        mock_node_1.name.return_value = "mgmt1-m2"
        mock_node_2 = Mock()
        mock_node_2.name.return_value = "mgmt1-m1"
        mock_node_3 = Mock()
        mock_node_3.name.return_value = "mgmt1-worker1"
        mock_node_4 = Mock()
        mock_node_4.name.return_value = "mgmt1-m3"
        return [mock_node_1, mock_node_2, mock_node_3, mock_node_4]

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="scenario_passed",
            tested_object_mock_dict={
                "_node_executors": {
                    "mgmt1-m2": Mock(),
                    "mgmt1-m1": Mock(),
                    "mgmt1-worker1": Mock(),
                    "mgmt1-m3": Mock(),
                },
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                        "ovnkube-node-927b4": "mgmt1-m1",
                        "ovnkube-node-cgnr8": "mgmt1-worker1",
                        "ovnkube-node-dmqk5": "mgmt1-m3",
                    }
                ),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="scenario_failed",
            tested_object_mock_dict={
                "_node_executors": {
                    "mgmt1-m2": Mock(),
                    "mgmt1-m1": Mock(),
                    "mgmt1-worker1": Mock(),
                    "mgmt1-m3": Mock(),
                },
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                        "ovnkube-node-927b4": "mgmt1-m1",
                    }
                ),
            },
            failed_msg="The following nodes are missing ovnkube-node pods: ['mgmt1-m3', 'mgmt1-worker1']",
        )
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestLogicalSwitchNodeValidator(OVNKubernetesTestBase):
    """Tests for LogicalSwitchNodeValidator validator."""

    tested_type = LogicalSwitchNodeValidator

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="scenario_passed",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                        "ovnkube-node-927b4": "mgmt1-m1",
                    }
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ovn-nbctl ls-list"): CmdOutput(
                    "dcd1b6b9-41e5-4591-976f-bdf738f80660 (mgmt1-m2)"
                ),
                ("openshift-ovn-kubernetes", "ovnkube-node-927b4", "ovn-nbctl ls-list"): CmdOutput(
                    "dcd1b6b9-41e5-4591-976f-bdf738f80660 (mgmt1-m1)"
                ),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="scenario_failed",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                        "ovnkube-node-927b4": "mgmt1-m1",
                    }
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ovn-nbctl ls-list"): CmdOutput(
                    "some-other-logical-switch (other-node)"
                ),
                ("openshift-ovn-kubernetes", "ovnkube-node-927b4", "ovn-nbctl ls-list"): CmdOutput(
                    "some-other-logical-switch (other-node)"
                ),
            },
            failed_msg="ovnkube-node ovnkube-node-7dphn: there is no logical switch with node name - mgmt1-m2\novnkube-node ovnkube-node-927b4: there is no logical switch with node name - mgmt1-m1",
        )
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
