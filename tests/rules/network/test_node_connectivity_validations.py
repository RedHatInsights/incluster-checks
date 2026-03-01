"""
Unit tests for node connectivity validations.

Tests for AreAllNodesConnected and VerifyBondedInterfacesUp validators.
Ported from: support/HealthChecks/tests/pytest/flows/network/test_network_validations.py
"""

from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.network.node_connectivity_validations import AreAllNodesConnected, VerifyBondedInterfacesUp
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


class NodeConnectivityTestBase(RuleTestBase):
    """Base class for node connectivity validator tests."""

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled",
            tested_object_mock_dict={"is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))},
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={"is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=True))},
        )
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)


class TestAreAllNodesConnected(RuleTestBase):
    """Tests for AreAllNodesConnected orchestrator validator."""

    tested_type = AreAllNodesConnected

    # Override fixture to create OrchestratorRule with node_executors
    @pytest.fixture
    def tested_object(self):
        """
        Create tested object (OrchestratorRule) with mock node_executors.

        Returns:
            Instance of AreAllNodesConnected
        """
        # For OrchestratorRule, we don't pass host_executor in constructor
        # Instead we create it and set node_executors directly
        tested_obj = self.tested_type()
        return tested_obj

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="all_nodes_connected",
            tested_object_mock_dict={
                "_node_executors": {
                    "workerbm-1": Mock(is_connected=True),
                    "workerbm-2": Mock(is_connected=True),
                }
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="one_node_not_connected",
            tested_object_mock_dict={
                "_node_executors": {
                    "workerbm-1": Mock(is_connected=True),
                    "workerbm-2": Mock(is_connected=False),
                }
            },
            failed_msg="Following nodes are not connected:\nworkerbm-2",
        ),
        RuleScenarioParams(
            scenario_title="all_nodes_not_connected",
            tested_object_mock_dict={
                "_node_executors": {
                    "workerbm-1": Mock(is_connected=False),
                    "workerbm-2": Mock(is_connected=False),
                }
            },
            failed_msg="Following nodes are not connected:\nworkerbm-1\nworkerbm-2",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestVerifyBondedInterfacesUp(NodeConnectivityTestBase):
    """Tests for VerifyBondedInterfacesUp validator."""

    tested_type = VerifyBondedInterfacesUp

    # Prerequisite scenarios - bonding directory exists/not exists
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "bonding_directory_not_exists",
            cmd_input_output_dict={
                "test -d /proc/net/bonding/": CmdOutput("", return_code=1),
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "bonding_directory_exists",
            cmd_input_output_dict={
                "test -d /proc/net/bonding/": CmdOutput("", return_code=0),
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="all_bonded_interfaces_up",
            cmd_input_output_dict={
                "ls /proc/net/bonding/": CmdOutput("bond0  bond1"),
                "cat /proc/net/bonding/bond0 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond0 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
                "cat /proc/net/bonding/bond1 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond1 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="bond0_master_down",
            cmd_input_output_dict={
                "ls /proc/net/bonding/": CmdOutput("bond0  bond1"),
                "cat /proc/net/bonding/bond0 | grep 'MII Status'": CmdOutput(
                    "MII Status: down\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond0 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
                "cat /proc/net/bonding/bond1 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond1 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
            },
            failed_msg="bond0: some bonded interfaces are down: ['master']",
        ),
        RuleScenarioParams(
            scenario_title="bond0_first_slave_down",
            cmd_input_output_dict={
                "ls /proc/net/bonding/": CmdOutput("bond0  bond1"),
                "cat /proc/net/bonding/bond0 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: down\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond0 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
                "cat /proc/net/bonding/bond1 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond1 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
            },
            failed_msg="bond0: some bonded interfaces are down: ['eno12409']",
        ),
        RuleScenarioParams(
            scenario_title="bond0_all_interfaces_down",
            cmd_input_output_dict={
                "ls /proc/net/bonding/": CmdOutput("bond0  bond1"),
                "cat /proc/net/bonding/bond0 | grep 'MII Status'": CmdOutput(
                    "MII Status: down\nMII Status: down\nMII Status: down"
                ),
                "cat /proc/net/bonding/bond0 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
                "cat /proc/net/bonding/bond1 | grep 'MII Status'": CmdOutput(
                    "MII Status: up\nMII Status: up\nMII Status: up"
                ),
                "cat /proc/net/bonding/bond1 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
            },
            failed_msg="bond0: some bonded interfaces are down: ['master', 'eno12409', 'eno12399']",
        ),
        RuleScenarioParams(
            scenario_title="multiple_bonds_with_issues",
            cmd_input_output_dict={
                "ls /proc/net/bonding/": CmdOutput("bond0  bond1"),
                "cat /proc/net/bonding/bond0 | grep 'MII Status'": CmdOutput(
                    "MII Status: down\nMII Status: up\nMII Status: down"
                ),
                "cat /proc/net/bonding/bond0 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
                "cat /proc/net/bonding/bond1 | grep 'MII Status'": CmdOutput(
                    "MII Status: down\nMII Status: down\nMII Status: down"
                ),
                "cat /proc/net/bonding/bond1 | grep 'Slave Interface'": CmdOutput(
                    "Slave Interface: eno12409\nSlave Interface: eno12399"
                ),
            },
            failed_msg=(
                "bond0: some bonded interfaces are down: ['master', 'eno12399']\n"
                "bond1: some bonded interfaces are down: ['master', 'eno12409', 'eno12399']"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
