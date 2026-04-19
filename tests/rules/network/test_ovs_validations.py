"""
Tests for OVS network validations.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/flows/network/test_ovs_validations.py
"""

from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.network.ovs_base import (
    IsOVNKubernetesCollector,
    NncpOvsBondVlanCollector,
    OvnSecondaryNetworkBridgesCollector,
)
from in_cluster_checks.rules.network.ovs_validations import (
    OvsBridgeInterfaceHealthCheck,
    OvsInterfaceAndPortFound,
    OvsPhysicalPortHealthCheck,
    OvsProfileActivationCheck,
    VlanOvsAttachmentCheck,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorTestBase,
    DataCollectorScenarioParams,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class OvnDetectingNodeRuleTestBase(RuleTestBase):
    """Base test class for OVN-Kubernetes node-level rules."""

    scenario_not_applicable = [
        RuleScenarioParams(
            "non-OVN-Kubernetes cluster",
            {},
            data_collector_dict={IsOVNKubernetesCollector: {"orchestrator": False}},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        """Test scenarios where rule is not applicable."""
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)


class TestOvsInterfaceAndPortFound(OvnDetectingNodeRuleTestBase):
    """Test OvsInterfaceAndPortFound validator."""

    tested_type = OvsInterfaceAndPortFound

    # Sample nmcli -t -f TYPE connection show output (all connections - active and inactive)
    nmcli_types_ovs = """ovs-interface
ovs-port
ovs-bridge
loopback
vlan
"""

    # Output missing ovs-interface type
    nmcli_types_no_interface = """ovs-port
ovs-bridge
loopback
"""

    # Output missing ovs-port type
    nmcli_types_no_port = """ovs-interface
ovs-bridge
loopback
"""

    scenario_passed = [
        RuleScenarioParams(
            "OVS interface and port types exist (active connections)",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_ovs)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "OVS interface and port types exist (inactive connections also checked)",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_ovs)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "OVS interface and port types exist with secondary network bridge",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_ovs)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm"}},
            },
        ),
        RuleScenarioParams(
            "OVS interface and port types exist with multiple secondary bridges",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_ovs)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm", "br-tenant"}},
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ovs-interface type missing",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_no_interface)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No ovs-interface type connection found in NetworkManager.",
        ),
        RuleScenarioParams(
            "ovs-port type missing",
            {
                "nmcli -t -f TYPE connection show": CmdOutput(nmcli_types_no_port)
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No ovs-port type connection found in NetworkManager.",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestIsOVNKubernetesCollector(DataCollectorTestBase):
    """Test IsOVNKubernetesCollector data collector."""

    tested_type = IsOVNKubernetesCollector

    # Mock network.operator/cluster CR
    network_mock_ovn = Mock()
    network_mock_ovn.model.spec.defaultNetwork.type = "OVNKubernetes"

    network_mock_other = Mock()
    network_mock_other.model.spec.defaultNetwork.type = "OpenShiftSDN"

    scenarios = [
        DataCollectorScenarioParams(
            "OVN-Kubernetes cluster",
            {},
            scenario_res=True,
        ),
        DataCollectorScenarioParams(
            "non-OVN cluster",
            {},
            scenario_res=False,
        ),
    ]

    # Set tested_object_mock_dict for each scenario
    scenarios[0].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=network_mock_ovn)}
    scenarios[1].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=network_mock_other)}

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNncpOvsBondVlanCollector(DataCollectorTestBase):
    """Test NncpOvsBondVlanCollector data collector."""

    tested_type = NncpOvsBondVlanCollector

    # Mock NNCP with OVS bond VLANs
    nncp_with_vlans = Mock()
    nncp_with_vlans.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "interfaces": [
                    {
                        "type": "ovs-bridge",
                        "bridge": {
                            "port": [
                                {"name": "bond0.110"},
                                {"name": "bond0.200"},
                            ]
                        },
                    }
                ]
            }
        }
    }

    scenarios = [
        DataCollectorScenarioParams(
            "OVS bond VLANs found",
            {},
            scenario_res={"bond0.110", "bond0.200"},
        ),
        DataCollectorScenarioParams(
            "no NNCPs",
            {},
            scenario_res=set(),
        ),
    ]

    # Set tested_object_mock_dict for each scenario
    scenarios[0].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_with_vlans])}
    scenarios[1].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[])}

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestOvnSecondaryNetworkBridgesCollector(DataCollectorTestBase):
    """Test OvnSecondaryNetworkBridgesCollector data collector."""

    tested_type = OvnSecondaryNetworkBridgesCollector

    # Mock NNCP with secondary network bridges (OVN localnet configuration)
    nncp_with_secondary_bridge = Mock()
    nncp_with_secondary_bridge.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "ovn": {
                    "bridge-mappings": [
                        {"bridge": "br-vm", "localnet": "localnet1"},
                    ]
                }
            }
        }
    }

    # Mock NNCP with multiple secondary bridges
    nncp_with_multiple_bridges = Mock()
    nncp_with_multiple_bridges.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "ovn": {
                    "bridge-mappings": [
                        {"bridge": "br-vm", "localnet": "localnet1"},
                        {"bridge": "br-tenant", "localnet": "localnet2"},
                    ]
                }
            }
        }
    }

    # Mock NNCP without bridge-mappings
    nncp_without_secondary_bridges = Mock()
    nncp_without_secondary_bridges.as_dict.return_value = {
        "spec": {
            "desiredState": {}
        }
    }

    # Mock NNCP with empty bridge-mappings list
    nncp_empty_mappings = Mock()
    nncp_empty_mappings.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "ovn": {
                    "bridge-mappings": []
                }
            }
        }
    }

    # Mock NNCP with incomplete mapping (missing localnet)
    nncp_missing_localnet = Mock()
    nncp_missing_localnet.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "ovn": {
                    "bridge-mappings": [
                        {"bridge": "br-vm"}
                    ]
                }
            }
        }
    }

    # Mock NNCP with incomplete mapping (missing bridge)
    nncp_missing_bridge = Mock()
    nncp_missing_bridge.as_dict.return_value = {
        "spec": {
            "desiredState": {
                "ovn": {
                    "bridge-mappings": [
                        {"localnet": "localnet1"}
                    ]
                }
            }
        }
    }

    scenarios = [
        DataCollectorScenarioParams(
            "single secondary network bridge found",
            {},
            scenario_res={"br-vm"},
        ),
        DataCollectorScenarioParams(
            "multiple secondary network bridges found",
            {},
            scenario_res={"br-vm", "br-tenant"},
        ),
        DataCollectorScenarioParams(
            "no secondary network bridges (no bridge-mappings)",
            {},
            scenario_res=set(),
        ),
        DataCollectorScenarioParams(
            "no NNCPs found",
            {},
            scenario_res=set(),
        ),
        DataCollectorScenarioParams(
            "empty bridge-mappings list",
            {},
            scenario_res=set(),
        ),
        DataCollectorScenarioParams(
            "incomplete mapping (missing localnet)",
            {},
            scenario_res=set(),
        ),
        DataCollectorScenarioParams(
            "incomplete mapping (missing bridge)",
            {},
            scenario_res=set(),
        ),
    ]

    # Set tested_object_mock_dict for each scenario
    scenarios[0].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_with_secondary_bridge])}
    scenarios[1].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_with_multiple_bridges])}
    scenarios[2].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_without_secondary_bridges])}
    scenarios[3].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[])}
    scenarios[4].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_empty_mappings])}
    scenarios[5].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_missing_localnet])}
    scenarios[6].tested_object_mock_dict = {"oc_api.select_resources": Mock(return_value=[nncp_missing_bridge])}

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestOvsPhysicalPortHealthCheck(OvnDetectingNodeRuleTestBase):
    """Test OvsPhysicalPortHealthCheck rule."""

    tested_type = OvsPhysicalPortHealthCheck

    # Healthy outputs - physical port with NO IP
    nmcli_good = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "ovs-if-phys0        uuid123                               ethernet       enp1s0\n"
        "bond0               uuid456                               bond           bond0\n"
    )
    link_good = "2: enp1s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
    addr_no_ip = (
        "2: enp1s0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
    )

    # Failure outputs
    nmcli_missing = (
        "NAME                UUID                                  TYPE           DEVICE\n"
        "bond0               uuid456                               bond           bond0\n"
    )
    link_down = "2: enp1s0: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"
    addr_has_ip = (
        "2: enp1s0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.0.0.5/24 brd 10.0.0.255 scope global enp1s0\n"
    )

    # JSON output from ovs-vsctl --format=json --columns=name,type list interface
    interfaces_json_single = """{"data":[["enp1s0",""],["patch-br-ex-to-br-int","patch"],["br-ex","internal"]]}"""
    interfaces_json_multiple = """{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],["br-ex","internal"]]}"""

    scenario_passed = [
        RuleScenarioParams(
            "single physical port UP with no IP",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("enp1s0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check (ls commands - more reliable in containers)
                "ls -d /sys/class/net/*/device": CmdOutput("/sys/class/net/enp1s0/device"),
                "ls -d /sys/class/net/*/bonding": CmdOutput(""),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show enp1s0": CmdOutput(link_good),
                "ip addr show enp1s0": CmdOutput(addr_no_ip),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "multiple physical ports all UP with no IP",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check (ls commands - more reliable in containers)
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond1": CmdOutput(
                    "4: bond1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:00 brd ff:ff:ff:ff:ff:ff\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "multi-bridge: both bridges healthy (bond0 on br-ex, bond1 on br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check (ls commands - more reliable in containers)
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond1": CmdOutput(
                    "4: bond1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:00 brd ff:ff:ff:ff:ff:ff\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "multi-bridge: both bridges healthy with secondary network bridge identified (br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check (ls commands - more reliable in containers)
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond1": CmdOutput(
                    "4: bond1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:00 brd ff:ff:ff:ff:ff:ff\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm"}},
            },
        ),
    ]

    # JSON for scenario with no physical ports
    interfaces_json_no_physical = """{"data":[["patch-br-ex-to-br-int","patch"],["ovn-k8s-mp0","internal"],["patch-br-int-to-br-ex","patch"]]}"""

    scenario_failed = [
        RuleScenarioParams(
            "physical port not found",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("patch-br-ex-to-br-int"),  # Only patch port, no physical
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),  # br-int also has no physical
                # New optimized hardware-backed check - no hardware interfaces found
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(""),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No OVS bridges with physical ports found",
        ),
        RuleScenarioParams(
            "physical port down",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("enp1s0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check
                "ls -d /sys/class/net/*/device": CmdOutput("/sys/class/net/enp1s0/device"),
                "ls -d /sys/class/net/*/bonding": CmdOutput(""),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show enp1s0": CmdOutput(link_down),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Physical port issues:\nenp1s0 interface is DOWN",
        ),
        RuleScenarioParams(
            "physical port has IP (incorrect)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("enp1s0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # New optimized hardware-backed check
                "ls -d /sys/class/net/*/device": CmdOutput("/sys/class/net/enp1s0/device"),
                "ls -d /sys/class/net/*/bonding": CmdOutput(""),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show enp1s0": CmdOutput(link_good),
                "ip addr show enp1s0": CmdOutput(addr_has_ip),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Physical port issues:\n"
                "enp1s0 has IP address 10.0.0.5/24 - "
                "physical OVS ports should not have IPs (IPs belong on the bridge interface)"
            ),
        ),
        RuleScenarioParams(
            "multiple physical ports - one down",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(interfaces_json_multiple),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Physical port issues:\nbond1 interface is DOWN",
        ),
        RuleScenarioParams(
            "multiple physical ports - one has IP",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(interfaces_json_multiple),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond1": CmdOutput(
                    "4: bond1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:00 brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 10.0.0.10/24 brd 10.0.0.255 scope global bond1\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Physical port issues:\n"
                "bond1 has IP address 10.0.0.10/24 - "
                "physical OVS ports should not have IPs (IPs belong on the bridge interface)"
            ),
        ),
        RuleScenarioParams(
            "multi-bridge: secondary bridge port down (bond1 on br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"],["br-vm","internal"]]}'
                ),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Physical port issues:\nbond1 interface is DOWN (on bridge br-vm)",
        ),
        RuleScenarioParams(
            "multi-bridge: secondary bridge port has IP (bond1 on br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"],["br-vm","internal"]]}'
                ),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show bond0": CmdOutput("3: bond0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond0": CmdOutput(
                    "3: bond0: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n"
                ),
                "ip link show bond1": CmdOutput("4: bond1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show bond1": CmdOutput(
                    "4: bond1: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
                    "    link/ether aa:bb:cc:dd:ee:00 brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.100.10/24 brd 192.168.100.255 scope global bond1\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Physical port issues:\n"
                "bond1 has IP address 192.168.100.10/24 - physical OVS ports should not have IPs "
                "(IPs belong on the bridge interface) (on bridge br-vm)"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestOvsBridgeInterfaceHealthCheck(OvnDetectingNodeRuleTestBase):
    """Test OvsBridgeInterfaceHealthCheck rule."""

    tested_type = OvsBridgeInterfaceHealthCheck

    # Healthy outputs - bridge with link-local IPs
    link_good = "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"

    # Multiple valid link-local IP ranges
    addr_good_169_254_169 = (
        "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 192.168.122.10/24 brd 192.168.122.255 scope global br-ex\n"
        "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
    )
    addr_good_169_254_0 = (
        "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 192.168.122.10/24 brd 192.168.122.255 scope global br-ex\n"
        "    inet 169.254.0.2/17 brd 169.254.127.255 scope global br-ex\n"
    )

    # Failure outputs
    link_down = "6: br-ex: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"
    addr_no_ip = (
        "6: br-ex: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
    )
    addr_wrong_subnet = (
        "6: br-ex: <BROADCAST,MULTICAST,UP> mtu 1500 state UP\n"
        "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
        "    inet 10.0.0.5/24 brd 10.0.0.255 scope global br-ex\n"
    )

    # JSON for bridge scenarios (bond1 is physical port)
    interfaces_json_bridge = """{"data":[["bond1",""],["patch-br-ex-to-br-int","patch"],["br-ex","internal"]]}"""

    scenario_passed = [
        RuleScenarioParams(
            "bridge healthy with 169.254.169.x IP",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_good_169_254_169),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "bridge healthy with 169.254.0.x IP",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_good_169_254_0),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "multi-bridge: both bridges healthy with link-local IPs",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"],["br-vm","internal"]]}'
                ),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput("6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-ex": CmdOutput(
                    "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.122.10/24 brd 192.168.122.255 scope global br-ex\n"
                    "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
                ),
                "ip link show br-vm": CmdOutput("7: br-vm: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-vm": CmdOutput(
                    "7: br-vm: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:4b brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.100.10/24 brd 192.168.100.255 scope global br-vm\n"
                    "    inet 169.254.169.10/29 brd 169.254.169.15 scope global br-vm\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "secondary network bridge (br-vm) without internal port - should pass",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                # Only br-ex has internal port (br-vm is secondary network without internal port)
                "ip link show br-ex": CmdOutput("6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-ex": CmdOutput(
                    "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm"}},
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "bridge not found (ovs-vsctl fails)",
            {
                "ovs-vsctl list-br": CmdOutput("", return_code=1),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No OVS external bridges found",
        ),
        RuleScenarioParams(
            "only br-int exists (integration bridge should be excluded)",
            {
                "ovs-vsctl list-br": CmdOutput("br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(""),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No OVS external bridges found",
        ),
        RuleScenarioParams(
            "bridge down",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput(link_down),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Bridge interface issue: br-ex interface is DOWN",
        ),
        RuleScenarioParams(
            "no IP address",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_no_ip),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Bridge interface issue: br-ex has no IP address (OVN not initialized)",
        ),
        RuleScenarioParams(
            "wrong IP subnet (not link-local)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond1\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput(link_good),
                "ip addr show br-ex": CmdOutput(addr_wrong_subnet),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Bridge interface issue: br-ex has unexpected IP addressing (10.0.0.5/24) - "
                "expected 169.254.x.x (link-local) for OVN"
            ),
        ),
        RuleScenarioParams(
            "multi-bridge: secondary bridge down (br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"],["br-vm","internal"]]}'
                ),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput("6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-ex": CmdOutput(
                    "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
                ),
                "ip link show br-vm": CmdOutput("7: br-vm: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="Bridge interface issues (checked 2 bridges):\nbr-vm interface is DOWN",
        ),
        RuleScenarioParams(
            "multi-bridge: secondary bridge missing link-local IP (br-vm)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"],["br-vm","internal"]]}'
                ),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput("6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-ex": CmdOutput(
                    "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
                ),
                "ip link show br-vm": CmdOutput("7: br-vm: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-vm": CmdOutput(
                    "7: br-vm: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:4b brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.100.10/24 brd 192.168.100.255 scope global br-vm\n"
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Bridge interface issues (checked 2 bridges):\n"
                "br-vm has unexpected IP addressing (192.168.100.10/24) - "
                "expected 169.254.x.x (link-local) for OVN"
            ),
        ),
        RuleScenarioParams(
            "bridge missing internal port (exists in OVS but no kernel interface)",
            {
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl --format=json --columns=name,type list interface": CmdOutput(
                    '{"data":[["bond0",""],["bond1",""],["patch-br-ex-to-br-int","patch"],'
                    '["patch-br-vm-to-br-int","patch"],["br-ex","internal"]]}'  # br-vm internal port missing
                ),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                "ls -d /sys/class/net/*/device": CmdOutput(
                    "/sys/class/net/bond0/device\n/sys/class/net/bond1/device"
                ),
                "ls -d /sys/class/net/*/bonding": CmdOutput(
                    "/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"
                ),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
                # VLAN check - no VLANs exist
                "ls /proc/net/vlan/*": CmdOutput("", return_code=2),
                "ip link show br-ex": CmdOutput("6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"),
                "ip addr show br-ex": CmdOutput(
                    "6: br-ex: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 52:54:00:3a:8a:3a brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 169.254.169.2/29 brd 169.254.169.7 scope global br-ex\n"
                ),
                "ip link show br-vm": CmdOutput(
                    "Device \"br-vm\" does not exist.\ncommand terminated with exit code 1",
                    return_code=1
                ),
                "ovs-appctl dpif/show": CmdOutput(
                    "system@ovs-system:\n"
                    "  br-ex:\n"
                    "    bond0 1/5: (system)\n"
                    "    br-ex 65534/6: (internal)\n"
                    "    patch-br-ex-to-br-int 2/none: (patch: peer=patch-br-int-to-br-ex)\n"
                    "  br-vm:\n"
                    "    bond1 1/1: (system)\n"
                    "    patch-br-vm-to-br-int 2/none: (patch: peer=patch-br-int-to-br-vm)\n"
                    # Note: br-vm has NO internal port line
                ),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Bridge interface issues (checked 2 bridges):\n"
                "br-vm exists in OVS database but missing internal port "
                "(kernel interface not created). Bridge has ports in OVS but NetworkManager "
                "failed to create the internal port. Check 'ovs-appctl dpif/show' and "
                "NetworkManager logs for activation errors."
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestVlanOvsAttachmentCheck(RuleTestBase):
    """Test VlanOvsAttachmentCheck rule."""

    tested_type = VlanOvsAttachmentCheck

    # Test data
    nmcli_active_with_vlan = "bond0.110:bond0.110\nbond0:bond0\n"
    nmcli_active_with_mixed_vlans = "bond0.110:bond0.110\nbond0.200:bond0.200\nbond0:bond0\n"  # OVS + storage
    nmcli_active_no_vlan = "bond0:bond0\n"
    ovs_ports_with_vlan = "bond0\nbond0.110\n"
    ovs_ports_missing_vlan = "bond0\n"

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no VLAN interfaces on this node",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_no_vlan),
                "ls /proc/net/vlan/*": CmdOutput("", return_code=1),  # No VLANs
            },
            failed_msg="No VLAN interfaces found on this node",
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "VLAN interfaces exist on this node",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),  # VLAN exists
            },
        ),
    ]

    # JSON for VLAN attachment scenarios
    interfaces_json_vlan_attached = """{"data":[["bond0",""],["bond0.110",""],["patch-br-ex-to-br-int","patch"],["br-ex","internal"]]}"""
    interfaces_json_vlan_detached = """{"data":[["bond0",""],["patch-br-ex-to-br-int","patch"],["br-ex","internal"]]}"""

    scenario_passed = [
        RuleScenarioParams(
            "NNCP bond VLAN attached to OVS",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond0.110\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
        RuleScenarioParams(
            "storage VLAN exists but correctly ignored (not in NNCP)",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_mixed_vlans),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\nvlan:bond0.200\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110\n/proc/net/vlan/bond0.200"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond0.110\npatch-br-ex-to-br-int"),  # Only bond0.110 in OVS
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
        RuleScenarioParams(
            "multi-bridge: VLAN attached to secondary bridge (bond0.110 on br-vm)",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput("bond0.110:bond0.110\nbond0:bond0\nbond1:bond1\n"),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\nbond:bond1\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\nbond0.110\npatch-br-vm-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
        RuleScenarioParams(
            "interface named like VLAN but not actual VLAN - filtered out",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput("fake.123:fake.123\nbond0.110:bond0.110\nbond0:bond0\n"),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("ovs-port:fake.123\nbond:bond0\novs-port:bond0.110\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\nbond0.110\nfake.123\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "VLAN interfaces exist but no OVS bridges",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("", return_code=1),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
            failed_msg="VLAN interfaces exist but no OVS bridges found - OVS may not be configured properly",
        ),
        RuleScenarioParams(
            "OVS VLAN interface detached from OVS",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),  # Missing bond0.110
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
            failed_msg="OVS-configured VLAN interface(s) detached from OVS bridge: bond0.110",
        ),
        RuleScenarioParams(
            "multi-bridge: VLAN detached from all bridges",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput("bond0.110:bond0.110\nbond0:bond0\nbond1:bond1\n"),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\novs-port:bond0.110\nbond:bond1\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
                "ovs-vsctl list-br": CmdOutput("br-ex\nbr-vm\nbr-int"),
                "ovs-vsctl list-ports br-ex": CmdOutput("bond0\npatch-br-ex-to-br-int"),
                "ovs-vsctl list-ports br-vm": CmdOutput("bond1\npatch-br-vm-to-br-int"),  # VLAN missing from both
                "ovs-vsctl list-ports br-int": CmdOutput("ovn-k8s-mp0\npatch-br-int-to-br-ex"),
                # Hardware-backed interface detection
                "ls -d /sys/class/net/*/device": CmdOutput(""),
                "ls -d /sys/class/net/*/bonding": CmdOutput("/sys/class/net/bond0/bonding\n/sys/class/net/bond1/bonding"),
                "ls -d /sys/class/net/*/team": CmdOutput(""),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
            failed_msg="OVS-configured VLAN interface(s) detached from OVS bridges (checked br-ex, br-vm): bond0.110",
        ),
    ]

    scenario_not_applicable = [
        RuleScenarioParams(
            "no NNCP OVS VLANs configured and no NM ovs-port VLANs",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput(nmcli_active_with_vlan),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\nvlan:bond0.110\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.110"),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": set()},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
        RuleScenarioParams(
            "NNCP VLANs not present on this node",
            {
                "nmcli -t -f NAME,DEVICE connection show --active": CmdOutput("bond0.200:bond0.200\nbond0:bond0\n"),
                "nmcli -t -f TYPE,DEVICE connection show --active": CmdOutput("bond:bond0\nvlan:bond0.200\n"),
                "ls /proc/net/vlan/*": CmdOutput("/proc/net/vlan/bond0.200"),
            },
            data_collector_dict={
                NncpOvsBondVlanCollector: {"orchestrator": {"bond0.110"}},
                IsOVNKubernetesCollector: {"orchestrator": True},
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test scenarios where prerequisites are not fulfilled."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test scenarios where prerequisites are fulfilled."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        """Test scenarios where rule is not applicable."""
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)

class TestOvsProfileActivationCheck(OvnDetectingNodeRuleTestBase):
    """Test OvsProfileActivationCheck rule."""

    tested_type = OvsProfileActivationCheck

    # Sample nmcli output with TYPE,DEVICE,STATE
    nmcli_all_activated = """ovs-interface:br-ex:activated
ovs-port:bond1:activated
ovs-bridge:br-ex:activated
bond:bond0:activated
loopback:lo:activated
"""

    nmcli_with_deactivated = """ovs-interface:br-ex:activated
ovs-port:bond1:deactivated
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    nmcli_no_ovs = """bond:bond0:activated
loopback:lo:activated
802-3-ethernet:eth0:activated
"""

    # Additional test scenarios - states: activated, deactivated, activating, deactivating
    nmcli_activating_in_progress = """ovs-interface:br-ex:activating
ovs-port:bond1:activated
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    nmcli_multiple_deactivated = """ovs-interface:br-ex:deactivated
ovs-port:bond1:deactivated
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    nmcli_deactivating = """ovs-interface:br-ex:activated
ovs-port:bond1:deactivating
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    nmcli_mixed_states = """ovs-interface:br-ex:deactivated
ovs-port:bond1:deactivating
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    nmcli_all_deactivated = """ovs-interface:br-ex:deactivated
ovs-port:bond1:deactivated
ovs-bridge:br-ex:deactivated
bond:bond0:activated
"""

    nmcli_empty_state = """ovs-interface:br-ex:
ovs-port:bond1:activated
ovs-bridge:br-ex:activated
bond:bond0:activated
"""

    scenario_passed = [
        RuleScenarioParams(
            "all OVS profiles activated",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_all_activated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "OVS profile in activating state (should pass - activation in progress)",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_activating_in_progress),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
        ),
        RuleScenarioParams(
            "all OVS profiles activated with secondary network bridge",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_all_activated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm"}},
            },
        ),
        RuleScenarioParams(
            "all OVS profiles activated with multiple secondary bridges",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_all_activated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": {"br-vm", "br-tenant"}},
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ovs-port profile deactivated",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_with_deactivated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 1 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - bond1 (type: ovs-port, state: deactivated)"
            ),
        ),
        RuleScenarioParams(
            "multiple OVS profiles deactivated",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_multiple_deactivated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 2 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - br-ex (type: ovs-interface, state: deactivated)\n"
                "  - bond1 (type: ovs-port, state: deactivated)"
            ),
        ),
        RuleScenarioParams(
            "OVS profile in deactivating state",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_deactivating),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 1 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - bond1 (type: ovs-port, state: deactivating)"
            ),
        ),
        RuleScenarioParams(
            "mixed inactive states (deactivated + deactivating)",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_mixed_states),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 2 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - br-ex (type: ovs-interface, state: deactivated)\n"
                "  - bond1 (type: ovs-port, state: deactivating)"
            ),
        ),
        RuleScenarioParams(
            "all OVS profiles deactivated",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_all_deactivated),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 3 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - br-ex (type: ovs-interface, state: deactivated)\n"
                "  - bond1 (type: ovs-port, state: deactivated)\n"
                "  - br-ex (type: ovs-bridge, state: deactivated)"
            ),
        ),
        RuleScenarioParams(
            "empty STATE field treated as inactive",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_empty_state),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg=(
                "Found 1 inactive OVS profile(s) out of 3 total.\n"
                "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.\n"
                "\n"
                "Inactive profiles:\n"
                "  - br-ex (type: ovs-interface, state: )"
            ),
        ),
    ]

    scenario_not_applicable = [
        RuleScenarioParams(
            "no OVS profiles on this node",
            {
                "nmcli -t -f TYPE,DEVICE,STATE connection show": CmdOutput(nmcli_no_ovs),
            },
            data_collector_dict={
                IsOVNKubernetesCollector: {"orchestrator": True},
                OvnSecondaryNetworkBridgesCollector: {"orchestrator": set()},
            },
            failed_msg="No OVS NetworkManager profiles found on this node",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """Test scenarios where rule should pass."""
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """Test scenarios where rule should fail."""
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        """Test scenarios where rule is not applicable."""
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)
