"""
Unit tests for Whereabouts IPAM validators.

Tests for WhereaboutsDuplicateIPAddresses, WhereaboutsMissingPodrefs,
WhereaboutsMissingAllocations, and WhereaboutsExistingAllocations rules.
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.network.whereabouts_validations import (
    WhereaboutsDuplicateIPAddresses,
    WhereaboutsExistingAllocations,
    WhereaboutsMissingAllocations,
    WhereaboutsMissingPodrefs,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleTestBase, RuleScenarioParams


class TestWhereaboutsDuplicateIPAddresses(RuleTestBase):
    """Tests for WhereaboutsDuplicateIPAddresses rule."""

    tested_type = WhereaboutsDuplicateIPAddresses

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled - no allocations",
            tested_object_mock_dict={
                "is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={
                "get_ippool_allocation_list": Mock(return_value=[
                    {"name": "ippool-1", "range": "10.0.0.0/24", "allocation_number": "5", "allocation_data": {}}
                ])
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            "pods have unique IPs",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                        {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                        {"name": "pod2", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.6"]}]},
                ]),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    scenario_failed = [
        RuleScenarioParams(
            "pods have duplicate IPs",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                        {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                        {"name": "pod2", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                ]),
            },
            failed_msg=(
                "Duplicate whereabouts IP addresses have been detected:\n"
                "--> Pod default/pod1 has a duplicate IP 10.0.0.5\n"
                "--> Pod default/pod2 has a duplicate IP 10.0.0.5"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestWhereaboutsMissingPodrefs(RuleTestBase):
    """Tests for WhereaboutsMissingPodrefs rule."""

    tested_type = WhereaboutsMissingPodrefs

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled - no allocations",
            tested_object_mock_dict={
                "is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={
                "get_ippool_allocation_list": Mock(return_value=[
                    {"name": "ippool-1", "range": "10.0.0.0/24", "allocation_number": "5", "allocation_data": {"podref": "default/pod1"}}
                ])
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            "all allocations have podrefs",
            tested_object_mock_dict={
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {"5": {"podref": "default/pod1"}}}}
                ]),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    scenario_failed = [
        RuleScenarioParams(
            "stale allocations without podrefs",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[]),
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {"5": {}}}}
                ]),
                "gather_pod_configs": Mock(return_value=[]),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestWhereaboutsMissingAllocations(RuleTestBase):
    """Tests for WhereaboutsMissingAllocations rule."""

    tested_type = WhereaboutsMissingAllocations

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled - no allocations",
            tested_object_mock_dict={
                "is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={
                "get_ippool_allocation_list": Mock(return_value=[
                    {"name": "ippool-1", "range": "10.0.0.0/24", "allocation_number": "5", "allocation_data": {}}
                ])
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            "all pod IPs have allocations",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {"5": {}}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                        {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                ]),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    scenario_failed = [
        RuleScenarioParams(
            "pod has IP without allocation",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                    {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},                ]),
            },
            failed_msg=(
                "Missing whereabouts ippool allocations have been detected:\n"
                "--> Pod default/pod1 has a missing IP allocation for IP 10.0.0.5"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestWhereaboutsExistingAllocations(RuleTestBase):
    """Tests for WhereaboutsExistingAllocations rule."""

    tested_type = WhereaboutsExistingAllocations

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "prerequisite_not_fulfilled - no allocations",
            tested_object_mock_dict={
                "is_prerequisite_fulfilled": Mock(return_value=Mock(fulfilled=False))
            },
        )
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "prerequisite_fulfilled",
            tested_object_mock_dict={
                "get_ippool_allocation_list": Mock(return_value=[
                    {"name": "ippool-1", "range": "10.0.0.0/24", "allocation_number": "5", "allocation_data": {"podref": "default/pod1"}}
                ])
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            "all allocations match their pods",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {"5": {"podref": "default/pod1"}}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                        {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                ]),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    scenario_failed = [
        RuleScenarioParams(
            "allocation points to wrong pod",
            tested_object_mock_dict={
                "gather_net_attach_def_configs": Mock(return_value=[
                    {"name": "macvlan-conf", "namespace": "default", "config": {"name": "macvlan", "ipam": {"type": "whereabouts"}}}
                ]),
                "gather_ippool_configs": Mock(return_value=[
                    {"name": "ippool-1", "namespace": "default", "spec": {"range": "10.0.0.0/24", "allocations": {"5": {"podref": "default/wrongpod"}}}}
                ]),
                "gather_pod_configs": Mock(return_value=[
                        {"name": "pod1", "namespace": "default", "network": [{"name": "default/macvlan-conf", "ips": ["10.0.0.5"]}]},
                ]),
            },
            failed_msg=(
                "There is a problem with the following ippool allocations. "
                "These allocations do not match their corresponding pod name and pod IP "
                "based on the allocation podrefs:\n"
                "--> Allocation in ippool ippool-1 with allocation number 5 "
                "does not match the pod listed in its podref: default/wrongpod"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
