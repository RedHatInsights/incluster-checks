"""
Tests for OVS network validations.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/flows/network/test_ovs_validations.py
"""

import pytest

from in_cluster_checks.rules.network.ovs_validations import (
    OvsInterfaceAndPortFound,
    Bond0Dns,
    Bond0DnsServersComparison,
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


class TestOvsInterfaceAndPortFound(RuleTestBase):
    """Test OvsInterfaceAndPortFound validator."""

    tested_type = OvsInterfaceAndPortFound

    # Sample nmcli connection show output
    nmcli_out = """        NAME                UUID                                  TYPE           DEVICE   .
ovs-if-br-ex        a003bd38-993b-4381-a045-a73cbb95d5a1  ovs-interface  br-ex    .
lo                  1cb462ac-9545-4df8-ab39-6b2b502d0b6d  loopback       lo       .
bond1.62            2741b63b-d8fd-597b-bb9a-ba40524d86a3  vlan           bond1.62 .
bond1.63            b04d9161-cbee-500f-80ec-63b61d24d7a7  vlan           bond1.63 .
bond1.64            0194209d-6bdd-5309-ae06-effdb22b83b7  vlan           bond1.64 .
br-ex               5d63c53e-6560-4d31-b00d-251652d1864d  ovs-bridge     br-ex    .
{}0        87e16a88-908a-4f07-ace4-797d12db7a52  vlan           bond0.61 .
ovs-port-br-ex      cf7a7335-b894-44c7-bb24-3691f90ab92a  ovs-port       br-ex    .
{}0      1ebbf722-3615-44b8-b379-b370e606a9a3  ovs-port       bond0.61 .
Wired connection 1  f149efb7-660c-3f27-abca-0017b5c485df  ethernet       --       .
bond0.61            0720fef3-957e-5bd2-a053-9a27413e3870  vlan           --       .
"""

    scenario_passed = [
        RuleScenarioParams(
            "ovs-if-phys and ovs-port-phys exist",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-if-phys", "ovs-port-phys")
                )
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ovs-if-phys does not exist and ovs-port-phys exists",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-vlan-phys", "ovs-port-phys")
                )
            },
        ),
        RuleScenarioParams(
            "ovs-if-phys and ovs-port-phys dont exist",
            {
                "nmcli connection show": CmdOutput(
                    nmcli_out.format("ovs-vlan-phys", "ovs-porti-phys")
                )
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestBond0Dns(DataCollectorTestBase):
    """Test Bond0Dns data collector."""

    tested_type = Bond0Dns

    # Sample nmcli conn show bond0 output
    out = """connection.id:                          bond0
802-3-ethernet.port:                    --
802-3-ethernet.speed:                   0-
802-3-ethernet.duplex:                  ---
ipv4.method:                            manual8.22.4
ipv4.dns:                               {}
ipv4.dns:                               {}
ipv4.dns:                               {}/0, nh = 172.31.41.1, mt = 0 table=254 }}
ipv4.dns-search:                        --2.31.41.8/24/0, nh = 172.31.41.1, mt = 0 table=254 }}
ipv6.method:                            manual023:22::4
ipv6.dns:                               {}
ipv6.dns-search:                        --
"""

    scenarios = [
        DataCollectorScenarioParams(
            "duplicate servers",
            {
                "nmcli conn show bond0": CmdOutput(
                    out.format(
                        "192.168.22.424",
                        "192.168.22.424",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                )
            },
            scenario_res={"ipv4": {"192.168.22.424"}, "ipv6": {"fd00:2023:22::4"}},
        ),
        DataCollectorScenarioParams(
            "different servers",
            {
                "nmcli conn show bond0": CmdOutput(
                    out.format(
                        "192.168.22.422",
                        "192.168.22.423",
                        "192.168.22.424",
                        "fd00:2023:22::4",
                    )
                )
            },
            scenario_res={
                "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                "ipv6": {"fd00:2023:22::4"},
            },
        ),
        DataCollectorScenarioParams(
            "no servers",
            {"nmcli conn show bond0": CmdOutput("some out")},
            scenario_res={"ipv4": set(), "ipv6": set()},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestBond0DnsServersComparison(RuleTestBase):
    """Test Bond0DnsServersComparison validator."""

    tested_type = Bond0DnsServersComparison

    scenario_passed = [
        RuleScenarioParams(
            "empty dns",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {"ipv4": set(), "ipv6": set()},
                    "manager1": {"ipv4": set(), "ipv6": set()},
                }
            },
        ),
        RuleScenarioParams(
            "equal dns",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                        "ipv6": {"fd00:2023:22::4"},
                    },
                    "manager1": {
                        "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                        "ipv6": {"fd00:2023:22::4"},
                    },
                }
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some empty dns",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {"ipv4": set(), "ipv6": set()},
                    "manager1": {
                        "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                        "ipv6": set(),
                    },
                    "manager2": {"ipv4": set(), "ipv6": set()},
                }
            },
            failed_msg="Mismatch in DNS server was found on:\nIPV4 DNS server isn't equal to host: manager0, server: []:\nhost: manager1 server: ['192.168.22.422', '192.168.22.423', '192.168.22.424']",
        ),
        RuleScenarioParams(
            "different dns",
            data_collector_dict={
                Bond0Dns: {
                    "manager0": {
                        "ipv4": {"192.168.22.422", "192.168.21.423", "192.168.22.424"},
                        "ipv6": {"fd00:2023:22::4"},
                    },
                    "manager1": {
                        "ipv4": {"192.168.22.422", "192.168.22.423", "192.168.22.424"},
                        "ipv6": {"fd00:2023:22::4"},
                    },
                }
            },
            failed_msg="Mismatch in DNS server was found on:\nIPV4 DNS server isn't equal to host: manager0, server: ['192.168.21.423', '192.168.22.422', '192.168.22.424']:\nhost: manager1 server: ['192.168.22.422', '192.168.22.423', '192.168.22.424']",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
