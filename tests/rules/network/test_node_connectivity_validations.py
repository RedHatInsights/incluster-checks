"""
Unit tests for node connectivity validations.

Tests for AreAllNodesConnected and VerifyBondedInterfacesUp validators.
Ported from: support/HealthChecks/tests/pytest/flows/network/test_network_validations.py
"""

from unittest.mock import Mock

import pytest

from tests.pytest_tools.test_data_collector_base import (
    DataCollectorTestBase,
    DataCollectorScenarioParams,
)
from in_cluster_checks.rules.network.node_connectivity_validations import (
    AreAllNodesConnected,
    VerifyBondedInterfacesUp,
    BondDnsCollector,
    BondDnsServersComparison
)
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
        # OrchestratorRule requires host_executor as first argument
        tested_obj = self.tested_type(host_executor=Mock())
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
                "test -d /proc/net/bonding": CmdOutput("", return_code=1),
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "bonding_directory_exists",
            cmd_input_output_dict={
                "test -d /proc/net/bonding": CmdOutput("", return_code=0),
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="all_bonded_interfaces_up",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0  bond1"),
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
                "ls /proc/net/bonding": CmdOutput("bond0  bond1"),
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
                "ls /proc/net/bonding": CmdOutput("bond0  bond1"),
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
                "ls /proc/net/bonding": CmdOutput("bond0  bond1"),
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
                "ls /proc/net/bonding": CmdOutput("bond0  bond1"),
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

class TestBondDnsServersComparison(RuleTestBase):
    """Test BondDnsServersComparison validator."""

    tested_type = BondDnsServersComparison

    scenario_not_applicable = [
        RuleScenarioParams(
            "no bond interfaces on any node",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": None,
                    "manager1": None,
                }
            },
            failed_msg="No bond interfaces found on any node",
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "empty dns across all bonds",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": {"bond0": {"ipv4": set(), "ipv6": set()}},
                    "manager1": {"bond0": {"ipv4": set(), "ipv6": set()}},
                }
            },
        ),
        RuleScenarioParams(
            "equal dns across all bonds",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": {"fd00:2023:22::4"},
                        },
                    },
                    "manager1": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": {"fd00:2023:22::4"},
                        },
                    },
                }
            },
        ),
        RuleScenarioParams(
            "equal dns on bond0 and bond0.110 (both TYPE=bond)",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                }
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "different dns on bond0",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": {
                        "bond0": {"ipv4": set(), "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {
                            "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                            "ipv6": set(),
                        },
                    },
                }
            },
            failed_msg=(
                "DNS server mismatch found across nodes:\n\n"
                "Bond interface: bond0\n"
                "  IPv4 DNS mismatch (reference: manager0 = []):\n"
                "    manager1: ['192.168.22.422', '192.168.22.423', '192.168.22.424']"
            ),
        ),
        RuleScenarioParams(
            "different dns on bond0.110 (TYPE=bond)",
            data_collector_dict={
                BondDnsCollector: {
                    "manager0": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                    },
                    "manager1": {
                        "bond0": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
                        "bond0.110": {"ipv4": {"1.1.1.1"}, "ipv6": set()},  # Different DNS
                    },
                }
            },
            failed_msg=(
                "DNS server mismatch found across nodes:\n\n"
                "Bond interface: bond0.110\n"
                "  IPv4 DNS mismatch (reference: manager0 = ['8.8.8.8']):\n"
                "    manager1: ['1.1.1.1']"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

class TestBondDnsCollector(DataCollectorTestBase):
    """Test BondDnsCollector data collector."""

    tested_type = BondDnsCollector

    # Sample nmcli -t -f TYPE,DEVICE connection show --active output
    # Note: bond0.110 shown with TYPE=bond is unusual but valid in some NetworkManager configs
    # (standard VLANs use TYPE=vlan, but this collector only processes TYPE=bond)
    nmcli_active = "bond:bond0\nbond:bond0.110\nethernet:eth0\n"
    nmcli_active_single = "bond:bond0\nethernet:eth0\n"

    # Sample nmcli conn show bond0 output
    bond0_out = """connection.id:                          bond0
802-3-ethernet.port:                    --
ipv4.method:                            manual
ipv4.dns:                               {}
ipv4.dns:                               {}
ipv4.dns:                               {}
ipv6.method:                            manual
ipv6.dns:                               {}
ipv6.dns-search:                        --
"""

    bond0_110_out = """connection.id:                          bond0.110
ipv4.method:                            manual
ipv4.dns:                               8.8.8.8
ipv6.method:                            manual
"""

    scenarios = [
        DataCollectorScenarioParams(
            "single bond with DNS",
            {
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput(nmcli_active_single),
                "nmcli conn show bond0": CmdOutput(
                    bond0_out.format(
                        "192.168.22.424",
                        "192.168.22.424",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                )
            },
            scenario_res={"bond0": {"ipv4": {"192.168.22.424"}, "ipv6": {"fd00:2023:22::4"}}},
        ),
        DataCollectorScenarioParams(
            "multiple bonds (bond0.110 with TYPE=bond)",
            {
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput(nmcli_active),
                "nmcli conn show bond0": CmdOutput(
                    bond0_out.format(
                        "192.168.22.422",
                        "192.168.22.423",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                ),
                "nmcli conn show bond0.110": CmdOutput(bond0_110_out),
            },
            scenario_res={
                "bond0": {
                    "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                    "ipv6": {"fd00:2023:22::4"},
                },
                "bond0.110": {"ipv4": {"8.8.8.8"}, "ipv6": set()},
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

