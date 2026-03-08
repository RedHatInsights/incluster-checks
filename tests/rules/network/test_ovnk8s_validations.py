"""
Unit tests for OVN-Kubernetes sanity check validations.

Tests for NodesHaveOvnkubeNodePod and LogicalSwitchNodeValidator.
Ported from: support/HealthChecks/tests/pytest/flows/network/test_ovnk8s_sanity_checks.py
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.network.ovnk8s_validations import (
    LogicalSwitchNodeValidator,
    MTUOverlayInterfaces,
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


IP_LINK_SHOW_ALL_MATCH = (
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
    "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
    "2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP\n"
    "    link/ether fa:16:3e:ab:cd:ef brd ff:ff:ff:ff:ff:ff\n"
    "3: ovs-system: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN\n"
    "4: br-int: <BROADCAST,MULTICAST> mtu 1400 qdisc noop state DOWN\n"
    "5: ovn-k8s-mp0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1400 qdisc noqueue state UNKNOWN\n"
)

IP_LINK_SHOW_MTU_MISMATCH = (
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
    "2: br-int: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN\n"
    "3: ovn-k8s-mp0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1400 qdisc noqueue state UNKNOWN\n"
)

IP_LINK_SHOW_NO_OVERLAY = (
    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN\n"
    "2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 9000 qdisc mq state UP\n"
)


class TestMTUOverlayInterfaces(OVNKubernetesTestBase):
    """Tests for MTUOverlayInterfaces validator."""

    tested_type = MTUOverlayInterfaces

    scenario_passed = [
        RuleScenarioParams(
            "all overlay interfaces have correct MTU",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                        "ovnkube-node-927b4": "mgmt1-m1",
                    }
                ),
                "_get_expected_mtu": Mock(return_value=1400),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ip link show"): CmdOutput(
                    IP_LINK_SHOW_ALL_MATCH
                ),
                ("openshift-ovn-kubernetes", "ovnkube-node-927b4", "ip link show"): CmdOutput(
                    IP_LINK_SHOW_ALL_MATCH
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "overlay interface has wrong MTU",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                    }
                ),
                "_get_expected_mtu": Mock(return_value=1400),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ip link show"): CmdOutput(
                    IP_LINK_SHOW_MTU_MISMATCH
                ),
            },
            failed_msg=(
                "[OVNKube Node: ovnkube-node-7dphn] MTU Mismatch: "
                "Expected (Network CR) = 1400, Actual (br-int) = 1500"
            ),
        ),
        RuleScenarioParams(
            "no overlay network interfaces found",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                    }
                ),
                "_get_expected_mtu": Mock(return_value=1400),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ip link show"): CmdOutput(
                    IP_LINK_SHOW_NO_OVERLAY
                ),
            },
            failed_msg="[OVNKube Node: ovnkube-node-7dphn] No overlay network interfaces found",
        ),
        RuleScenarioParams(
            "ip link show command fails",
            tested_object_mock_dict={
                "get_ovn_pod_to_node_dict": Mock(
                    return_value={
                        "ovnkube-node-7dphn": "mgmt1-m2",
                    }
                ),
                "_get_expected_mtu": Mock(return_value=1400),
            },
            rsh_cmd_output_dict={
                ("openshift-ovn-kubernetes", "ovnkube-node-7dphn", "ip link show"): CmdOutput(
                    "", return_code=1, err="command not found"
                ),
            },
            failed_msg="[OVNKube Node: ovnkube-node-7dphn] Failed to run ip link show: command not found",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
