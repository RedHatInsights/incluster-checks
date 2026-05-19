"""
Unit tests for DNS reachability validations.

Tests for DnsReachabilityCollector and VerifyDnsReachability validators.
"""

import json
from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.network.dns_validations import DnsReachabilityCollector, VerifyDnsReachability
from tests.pytest_tools.test_data_collector_base import DataCollectorScenarioParams, DataCollectorTestBase
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


class TestDnsReachabilityCollector(DataCollectorTestBase):
    """Tests for DnsReachabilityCollector data collector."""

    tested_type = DnsReachabilityCollector

    # Test data with DNS servers to test
    dns_servers = ["192.168.1.1", "8.8.8.8"]
    test_domain = "cluster.local"

    scenarios = [
        DataCollectorScenarioParams(
            "dns_servers_all_reachable",
            {
                "dig +short +time=2 +tries=1 @192.168.1.1 cluster.local": CmdOutput("10.0.0.1\n"),
                "dig +short +time=2 +tries=1 @8.8.8.8 cluster.local": CmdOutput("10.0.0.1\n"),
            },
            scenario_res={
                "reachable": ["192.168.1.1", "8.8.8.8"],
                "unreachable": [],
            },
        ),
        DataCollectorScenarioParams(
            "dns_servers_some_unreachable",
            {
                "dig +short +time=2 +tries=1 @192.168.1.1 cluster.local": CmdOutput("10.0.0.1\n"),
                "dig +short +time=2 +tries=1 @8.8.8.8 cluster.local": CmdOutput("", return_code=1),
            },
            scenario_res={
                "reachable": ["192.168.1.1"],
                "unreachable": ["8.8.8.8"],
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test collect_data with dns_servers and test_domain parameters."""
        self._init_data_collector_object(tested_object, scenario_params)
        result = tested_object.collect_data(
            dns_servers=self.dns_servers, test_domain=self.test_domain
        )
        assert result == scenario_params.scenario_res, (
            f"Data collector result mismatch for scenario: {scenario_params.scenario_title}\n"
            f"Expected: {scenario_params.scenario_res}\n"
            f"Got: {result}"
        )


class TestVerifyDnsReachability(RuleTestBase):
    """Tests for VerifyDnsReachability orchestrator validator."""

    tested_type = VerifyDnsReachability

    # DNS operator config with upstream resolvers
    dns_config_with_upstreams = json.dumps(
        {
            "spec": {
                "upstreamResolvers": {
                    "upstreams": [
                        {"type": "Network", "address": "192.168.1.1", "port": 53},
                        {"type": "Network", "address": "8.8.8.8", "port": 53},
                    ]
                }
            }
        }
    )

    # DNS operator config without upstream resolvers
    dns_config_no_upstreams = json.dumps({"spec": {}})

    @pytest.fixture
    def tested_object(self):
        """Create tested object (OrchestratorRule)."""
        tested_obj = self.tested_type(host_executor=Mock())
        # Mock oc_api
        tested_obj.oc_api = Mock()
        return tested_obj

    scenario_passed = [
        RuleScenarioParams(
            scenario_title="upstream_resolvers_all_reachable",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_with_upstreams, "")),
                "_get_search_domain_from_nodes": Mock(return_value="cluster.local"),
                "run_data_collector": Mock(
                    return_value={
                        "node-1": {
                            "reachable": ["192.168.1.1", "8.8.8.8"],
                            "unreachable": [],
                        },
                        "node-2": {
                            "reachable": ["192.168.1.1", "8.8.8.8"],
                            "unreachable": [],
                        },
                    }
                ),
                "get_data_collector_exceptions": Mock(return_value={}),
            },
        ),
        RuleScenarioParams(
            scenario_title="no_upstreams_resolv_conf_reachable",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_no_upstreams, "")),
                "_get_nameservers_from_nodes": Mock(return_value=["192.168.1.1"]),
                "_get_search_domain_from_nodes": Mock(return_value="cluster.local"),
                "run_data_collector": Mock(
                    return_value={
                        "node-1": {"reachable": ["192.168.1.1"], "unreachable": []},
                        "node-2": {"reachable": ["192.168.1.1"], "unreachable": []},
                    }
                ),
                "get_data_collector_exceptions": Mock(return_value={}),
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            scenario_title="upstream_resolvers_partial_reachability",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_with_upstreams, "")),
                "_get_search_domain_from_nodes": Mock(return_value="cluster.local"),
                "run_data_collector": Mock(
                    return_value={
                        "node-1": {"reachable": ["192.168.1.1"], "unreachable": ["8.8.8.8"]},
                        "node-2": {"reachable": ["8.8.8.8"], "unreachable": ["192.168.1.1"]},
                    }
                ),
                "get_data_collector_exceptions": Mock(return_value={}),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            scenario_title="upstream_resolvers_all_unreachable",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_with_upstreams, "")),
                "_get_search_domain_from_nodes": Mock(return_value="cluster.local"),
                "run_data_collector": Mock(
                    return_value={
                        "node-1": {"reachable": [], "unreachable": ["192.168.1.1", "8.8.8.8"]},
                        "node-2": {"reachable": [], "unreachable": ["192.168.1.1", "8.8.8.8"]},
                    }
                ),
                "get_data_collector_exceptions": Mock(return_value={}),
            },
            failed_msg=(
                "DNS servers from DNS operator upstream resolvers unreachable from all nodes: "
                "192.168.1.1, 8.8.8.8\n"
                "Per-node details:\n"
                "  - node-1: 192.168.1.1, 8.8.8.8\n"
                "  - node-2: 192.168.1.1, 8.8.8.8"
            ),
        ),
        RuleScenarioParams(
            scenario_title="no_dns_servers_found",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_no_upstreams, "")),
                "_get_nameservers_from_nodes": Mock(return_value=[]),
            },
            failed_msg=(
                "No DNS servers found. "
                "Neither upstream DNS resolvers configured nor nameservers in /etc/resolv.conf."
            ),
        ),
        RuleScenarioParams(
            scenario_title="data_collection_failed",
            tested_object_mock_dict={
                "oc_api.run_oc_command": Mock(return_value=(0, dns_config_with_upstreams, "")),
                "_get_search_domain_from_nodes": Mock(return_value="cluster.local"),
                "run_data_collector": Mock(return_value={}),
                "get_data_collector_exceptions": Mock(
                    return_value={"node-1": Exception("Connection failed")}
                ),
            },
            failed_msg=(
                "Failed to test DNS reachability from 1 node(s): node-1. "
                "Cannot verify DNS reachability with incomplete data."
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
