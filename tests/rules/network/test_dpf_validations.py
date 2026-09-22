"""Unit tests for DPF validation checks."""

import pytest

from in_cluster_checks.rules.network.dpf_validations import DpuBondLacpHealth, OvnGeneveTunnelLocalIp
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


BOND_LACP_HEALTHY = """Ethernet Channel Bonding Driver: v5.14.0-570.64.1.el9_6.x86_64

Bonding Mode: IEEE 802.3ad Dynamic link aggregation
Transmit Hash Policy: layer3+4 (1)
MII Status: up
MII Polling Interval (ms): 100
Up Delay (ms): 0
Down Delay (ms): 0

802.3ad info
LACP active: on
LACP rate: slow
Min links: 0
Aggregator selection policy (ad_select): stable

Slave Interface: ens7f0np0
MII Status: up
Speed: 200000 Mbps
Duplex: full
Link Failure Count: 0
Permanent HW addr: c4:70:bd:c2:c1:68
Slave queue ID: 0
Aggregator ID: 1
Actor Churn State: none
Partner Churn State: none

Slave Interface: ens7f1np1
MII Status: up
Speed: 200000 Mbps
Duplex: full
Link Failure Count: 0
Permanent HW addr: c4:70:bd:c2:c1:69
Slave queue ID: 0
Aggregator ID: 1
Actor Churn State: none
Partner Churn State: none
"""

BOND_LACP_SLAVE_DOWN = """Ethernet Channel Bonding Driver: v5.14.0-570.64.1.el9_6.x86_64

Bonding Mode: IEEE 802.3ad Dynamic link aggregation
Transmit Hash Policy: layer3+4 (1)
MII Status: up
MII Polling Interval (ms): 100

802.3ad info
LACP active: on

Slave Interface: ens7f0np0
MII Status: up
Speed: 200000 Mbps
Duplex: full
Link Failure Count: 0
Aggregator ID: 1
Actor Churn State: none
Partner Churn State: none

Slave Interface: ens7f1np1
MII Status: down
Speed: Unknown
Duplex: Unknown
Link Failure Count: 1
Aggregator ID: 2
Actor Churn State: churned
Partner Churn State: churned
"""

BOND_LACP_DIFFERENT_AGGREGATORS = """Ethernet Channel Bonding Driver: v5.14.0-570.64.1.el9_6.x86_64

Bonding Mode: IEEE 802.3ad Dynamic link aggregation
Transmit Hash Policy: layer3+4 (1)
MII Status: up

802.3ad info
LACP active: on

Slave Interface: ens7f0np0
MII Status: up
Speed: 200000 Mbps
Duplex: full
Aggregator ID: 1
Actor Churn State: none
Partner Churn State: churned

Slave Interface: ens7f1np1
MII Status: up
Speed: 200000 Mbps
Duplex: full
Aggregator ID: 2
Actor Churn State: none
Partner Churn State: churned
"""

BOND_LACP_SINGLE_SLAVE = """Ethernet Channel Bonding Driver: v5.14.0-570.64.1.el9_6.x86_64

Bonding Mode: IEEE 802.3ad Dynamic link aggregation
Transmit Hash Policy: layer3+4 (1)
MII Status: up

802.3ad info
LACP active: on

Slave Interface: ens7f0np0
MII Status: up
Speed: 200000 Mbps
Duplex: full
Aggregator ID: 1
Actor Churn State: none
Partner Churn State: none
"""

BOND_ACTIVE_BACKUP = """Ethernet Channel Bonding Driver: v5.14.0-570.64.1.el9_6.x86_64

Bonding Mode: fault-tolerance (active-backup)
Primary Slave: None
Currently Active Slave: ens7f0np0
MII Status: up

Slave Interface: ens7f0np0
MII Status: up
Speed: 200000 Mbps

Slave Interface: ens7f1np1
MII Status: up
Speed: 200000 Mbps
"""


class TestDpuBondLacpHealth(RuleTestBase):
    """Tests for DpuBondLacpHealth validator."""

    tested_type = DpuBondLacpHealth

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no_bonding_directory",
            cmd_input_output_dict={
                "test -d /proc/net/bonding": CmdOutput("", return_code=1),
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "bonding_directory_exists",
            cmd_input_output_dict={
                "test -d /proc/net/bonding": CmdOutput(""),
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="lacp_bond_healthy_two_slaves",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0"),
                "cat /proc/net/bonding/bond0": CmdOutput(BOND_LACP_HEALTHY),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="lacp_slave_down",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0"),
                "cat /proc/net/bonding/bond0": CmdOutput(BOND_LACP_SLAVE_DOWN),
            },
            failed_msg="LACP bond issues detected:\n  - bond0: slave(s) down: ens7f1np1\n  - bond0: slaves in different aggregators (ens7f0np0=agg1, ens7f1np1=agg2), LACP not fully negotiated\n  - bond0: LACP churn detected: ens7f1np1 actor=churned, ens7f1np1 partner=churned",
        ),
        RuleScenarioParams(
            scenario_title="lacp_different_aggregators",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0"),
                "cat /proc/net/bonding/bond0": CmdOutput(BOND_LACP_DIFFERENT_AGGREGATORS),
            },
            failed_msg="LACP bond issues detected:\n  - bond0: slaves in different aggregators (ens7f0np0=agg1, ens7f1np1=agg2), LACP not fully negotiated\n  - bond0: LACP churn detected: ens7f0np0 partner=churned, ens7f1np1 partner=churned",
        ),
        RuleScenarioParams(
            scenario_title="lacp_single_slave",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0"),
                "cat /proc/net/bonding/bond0": CmdOutput(BOND_LACP_SINGLE_SLAVE),
            },
            failed_msg="LACP bond issues detected:\n  - bond0: only 1 slave(s), expected 2+ for LACP",
        ),
    ]

    scenario_not_applicable = []

    scenario_skip = [
        RuleScenarioParams(
            scenario_title="non_lacp_bond_only_active_backup",
            cmd_input_output_dict={
                "ls /proc/net/bonding": CmdOutput("bond0"),
                "cat /proc/net/bonding/bond0": CmdOutput(BOND_ACTIVE_BACKUP),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_skip)
    def test_scenario_skip(self, scenario_params, tested_object):
        """Test that non-LACP bonds result in SKIP."""
        from in_cluster_checks.utils.enums import Status

        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()
            assert result.status == Status.SKIP, (
                f"Expected SKIP for scenario: {scenario_params.scenario_title}, got {result.status}"
            )

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not fulfilled when no bond interfaces exist."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is fulfilled when bond interfaces exist."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that healthy LACP bonds pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that degraded LACP bonds are detected and reported."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        """Test that non-applicable scenarios are handled correctly."""
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)


OVS_SHOW_WITH_GENEVE = """Bridge br-int
    Port ovn-abc123-0
        Interface ovn-abc123-0
            type: geneve
            options: {csum="true", key=flow, local_ip="10.6.135.202", remote_ip="10.6.135.236"}
    Port ovn-def456-0
        Interface ovn-def456-0
            type: geneve
            options: {csum="true", key=flow, local_ip="10.6.135.202", remote_ip="10.6.135.225"}
"""

OVS_SHOW_STALE_LOCAL_IP = """Bridge br-int
    Port ovn-abc123-0
        Interface ovn-abc123-0
            type: geneve
            options: {csum="true", key=flow, local_ip="10.6.135.1", remote_ip="10.6.135.236"}
"""

OVS_SHOW_MULTI_LOCAL_IP = """Bridge br-int
    Port ovn-abc123-0
        Interface ovn-abc123-0
            type: geneve
            options: {csum="true", key=flow, local_ip="10.6.135.202", remote_ip="10.6.135.236"}
    Port ovn-abc124-0
        Interface ovn-abc124-0
            type: geneve
            options: {csum="true", key=flow, local_ip="10.6.135.1", remote_ip="10.6.135.225"}
"""

OVS_SHOW_NO_GENEVE = """Bridge br-ex
    Port br-ex
        Interface br-ex
            type: internal
"""


class TestOvnGeneveTunnelLocalIp(RuleTestBase):
    """Tests for OvnGeneveTunnelLocalIp validator."""

    tested_type = OvnGeneveTunnelLocalIp

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "ovs_not_accessible",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput("", return_code=1),
            },
        ),
        RuleScenarioParams(
            "no_geneve_tunnels",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_NO_GENEVE),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "geneve_tunnels_present",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_WITH_GENEVE),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="local_ip_matches_node_ip",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_WITH_GENEVE),
                "cat /run/nodeip-configuration/primary-ip": CmdOutput("10.6.135.202"),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="multiple_local_ips_inconsistent",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_MULTI_LOCAL_IP),
                "cat /run/nodeip-configuration/primary-ip": CmdOutput("10.6.135.202"),
            },
            failed_msg=(
                "Multiple different local_ip values in Geneve tunnels: ['10.6.135.1', '10.6.135.202']. "
                "OVS configuration may be inconsistent."
            ),
        ),
        RuleScenarioParams(
            scenario_title="local_ip_stale_after_ip_change",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_STALE_LOCAL_IP),
                "cat /run/nodeip-configuration/primary-ip": CmdOutput("10.6.156.21"),
            },
            failed_msg=(
                "Geneve tunnel local_ip (10.6.135.1) does not match "
                "node primary IP (10.6.156.21). "
                "Inter-node pod connectivity may be broken."
            ),
        ),
    ]

    scenario_skip = [
        RuleScenarioParams(
            scenario_title="cannot_determine_node_ip",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput(OVS_SHOW_WITH_GENEVE),
                "cat /run/nodeip-configuration/primary-ip": CmdOutput("", return_code=1),
            },
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            scenario_title="ovs_fails_after_prerequisite_passed",
            cmd_input_output_dict={
                "ovs-vsctl show": CmdOutput("", return_code=1),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not fulfilled when OVS is unavailable or has no Geneve tunnels."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is fulfilled when Geneve tunnels are present."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test that matching local_ip and node IP passes."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test that stale or inconsistent local_ip values are detected."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        """Test that ovs-vsctl failure in run_rule raises UnExpectedSystemOutput."""
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_skip)
    def test_scenario_skip_geneve(self, scenario_params, tested_object):
        """Test that missing node IP results in SKIP."""
        from in_cluster_checks.utils.enums import Status

        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()
            assert result.status == Status.SKIP, (
                f"Expected SKIP for scenario: {scenario_params.scenario_title}, got {result.status}"
            )
