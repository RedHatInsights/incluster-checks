import pytest

from in_cluster_checks.rules.resources_utilization.resources_utilization import (
    ResourcesUtilization,
    NodeResourcesCollector,
)
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase

def _create_node_data(
    name: str,
    roles: list,
    cpu_capacity: str = "8",
    memory_capacity: str = "32Gi",
    cpu_allocatable: str = "7800m",
    memory_allocatable: str = "30Gi",
    cpu_requests: str = "100m",
    cpu_requests_pct: str = "1%",
    cpu_limits: str = "200m",
    cpu_limits_pct: str = "2%",
    memory_requests: str = "1Gi",
    memory_requests_pct: str = "3%",
    memory_limits: str = "2Gi",
    memory_limits_pct: str = "6%",
    extended_resources: dict | None = None,
    error: str = None,
) -> dict:
    """Generate node data for test scenarios.

    Args:
        name: Node name
        roles: List of node roles
        cpu_capacity: CPU capacity
        memory_capacity: Memory capacity
        cpu_allocatable: CPU allocatable
        memory_allocatable: Memory allocatable
        cpu_requests: CPU requests value
        cpu_requests_pct: CPU requests percentage
        cpu_limits: CPU limits value
        cpu_limits_pct: CPU limits percentage
        memory_requests: Memory requests value
        memory_requests_pct: Memory requests percentage
        memory_limits: Memory limits value
        memory_limits_pct: Memory limits percentage
        extended_resources: Dict of extended resources (e.g., {"nvidia.com/gpu": {...}})
        error: Error message if oc describe failed

    Returns:
        Node data dictionary
    """
    capacity = {"cpu": cpu_capacity, "memory": memory_capacity}
    allocatable = {"cpu": cpu_allocatable, "memory": memory_allocatable}
    allocated = {
        "cpu": {
            "requests": cpu_requests,
            "requests_percentage": cpu_requests_pct,
            "limits": cpu_limits,
            "limits_percentage": cpu_limits_pct,
        },
        "memory": {
            "requests": memory_requests,
            "requests_percentage": memory_requests_pct,
            "limits": memory_limits,
            "limits_percentage": memory_limits_pct,
        },
    }

    # Add extended resources to capacity, allocatable, and allocated
    if extended_resources:
        for resource_name, resource_data in extended_resources.items():
            capacity[resource_name] = resource_data["capacity"]
            allocatable[resource_name] = resource_data["allocatable"]
            allocated[resource_name] = {
                "requests": resource_data["requests"],
                "requests_percentage": resource_data["requests_pct"],
                "limits": resource_data["limits"],
                "limits_percentage": resource_data["limits_pct"],
            }

    node_data = {
        "name": name,
        "roles": roles,
        "schedulable": True,
        "capacity": capacity,
        "allocatable": allocatable,
        "allocated": allocated if not error else {},
    }

    if error:
        node_data["error"] = error

    return node_data


class TestResourcesUtilization(RuleTestBase):
    """Test ResourcesUtilization orchestrator."""

    tested_type = ResourcesUtilization


    def _assert_required_fields(self, data_dict, required_fields, context=""):
        """Assert all required fields exist in data dictionary.

        Args:
            data_dict: Dictionary to check
            required_fields: List of required field names
            context: Optional context string for error message
        """
        assert set(required_fields).issubset(data_dict.keys()), (
            f"Missing fields{' in ' + context if context else ''}. "
            f"Expected: {required_fields}, Got: {list(data_dict.keys())}"
        )
    

    merged_node_data_healthy = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
                memory_requests="128Mi",
            ),
            _create_node_data(
                name="master-1",
                roles=["control-plane", "master"],
                cpu_capacity="16",
                memory_capacity="64Gi",
                cpu_allocatable="15800m",
                memory_allocatable="62Gi",
                cpu_requests="550m",
                cpu_requests_pct="3%",
                cpu_limits="1000m",
                cpu_limits_pct="6%",
                memory_requests_pct="8%",
                memory_limits_pct="16%",
            ),
        ]
    }

    merged_node_data_high_cpu_requests = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
                cpu_requests="6800m",
                cpu_requests_pct="87%",
                cpu_limits="2660m",
                cpu_limits_pct="35%",
            ),
        ]
    }

    merged_node_data_high_memory_limits = {
        "nodes": [
            _create_node_data(
                name="master-1",
                roles=["control-plane", "master"],
                cpu_capacity="16",
                memory_capacity="64Gi",
                cpu_allocatable="15800m",
                memory_allocatable="62Gi",
                cpu_requests="550m",
                cpu_requests_pct="3%",
                cpu_limits="1000m",
                cpu_limits_pct="6%",
                memory_requests="5Gi",
                memory_requests_pct="8%",
                memory_limits="55Gi",
                memory_limits_pct="88%",
            ),
        ]
    }

    merged_node_data_multiple_high_resources = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
                cpu_requests="6800m",
                cpu_requests_pct="87%",
                cpu_limits="7500m",
                cpu_limits_pct="96%",
                memory_requests="28Gi",
                memory_requests_pct="93%",
                memory_limits="29Gi",
                memory_limits_pct="96%",
            ),
        ]
    }

    merged_node_data_multiple_nodes_high = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
                cpu_requests="6800m",
                cpu_requests_pct="87%",
                cpu_limits="2660m",
                cpu_limits_pct="35%",
            ),
            _create_node_data(
                name="worker-2",
                roles=["worker"],
                memory_requests="28Gi",
                memory_requests_pct="93%",
            ),
        ]
    }

    merged_node_data_extended_resources = {
        "nodes": [
            _create_node_data(
                name="gpu-worker-1",
                roles=["worker"],
                extended_resources={
                    "nvidia.com/gpu": {
                        "capacity": "4",
                        "allocatable": "4",
                        "requests": "4",
                        "requests_pct": "100%",
                        "limits": "0",
                        "limits_pct": "0%",
                    }
                },
            ),
        ]
    }

    merged_node_data_high_and_failures = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
                cpu_requests="6800m",
                cpu_requests_pct="87%",
                cpu_limits="2660m",
                cpu_limits_pct="35%",
            ),
            _create_node_data(
                name="worker-2",
                roles=["worker"],
                error="connection timeout",
            ),
            _create_node_data(
                name="worker-3",
                roles=["worker"],
                error="node not ready",
            ),
        ]
    }

    merged_node_data_with_failures = {
        "nodes": [
            _create_node_data(
                name="worker-1",
                roles=["worker"],
            ),
            _create_node_data(
                name="worker-2",
                roles=["worker"],
                error="connection timeout",
            ),
        ]
    }

    scenario_info = [
        RuleScenarioParams(
            "healthy cluster - low utilization levels",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_healthy},
            },
            info_msg="Resources utilization: 2 nodes, healthy utilization levels",
        ),
        RuleScenarioParams(
            "high CPU requests utilization on one node",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_high_cpu_requests},
            },
            info_msg="Resources utilization: 1 nodes, 1 node(s) with high utilization:\nworker-1: cpu requests at 6.8 cores (87%)",
        ),
        RuleScenarioParams(
            "high memory limits utilization on one node",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_high_memory_limits},
            },
            info_msg="Resources utilization: 1 nodes, 1 node(s) with high utilization:\nmaster-1: memory limits at 55Gi (88%)",
        ),
        RuleScenarioParams(
            "healthy utilization with oc describe failures",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_with_failures},
            },
            info_msg="Resources utilization: 2 nodes, healthy utilization levels.\nFailed to get allocated resources (oc describe) for: worker-2",
        ),
        RuleScenarioParams(
            "multiple high resources on single node (both requests and limits)",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_multiple_high_resources},
            },
            info_msg="Resources utilization: 1 nodes, 1 node(s) with high utilization:\nworker-1: cpu requests at 6.8 cores (87%)\nworker-1: cpu limits at 7.5 cores (96%)\nworker-1: memory requests at 28Gi (93%)\nworker-1: memory limits at 29Gi (96%)",
        ),
        RuleScenarioParams(
            "multiple nodes with high utilization",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_multiple_nodes_high},
            },
            info_msg="Resources utilization: 2 nodes, 2 node(s) with high utilization:\nworker-1: cpu requests at 6.8 cores (87%)\nworker-2: memory requests at 28Gi (93%)",
        ),
        RuleScenarioParams(
            "high utilization on extended resources (GPU)",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_extended_resources},
            },
            info_msg="Resources utilization: 1 nodes, 1 node(s) with high utilization:\ngpu-worker-1: nvidia.com/gpu requests at 4 (100%)",
        ),
        RuleScenarioParams(
            "high utilization with multiple oc describe failures",
            cmd_input_output_dict={},
            data_collector_dict={
                NodeResourcesCollector: {"in-cluster-orchestrator": merged_node_data_high_and_failures},
            },
            info_msg="Resources utilization: 3 nodes, 1 node(s) with high utilization:\nworker-1: cpu requests at 6.8 cores (87%).\nFailed to get allocated resources (oc describe) for: worker-2, worker-3",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_info)
    def test_scenario_info(self, scenario_params, tested_object):
        """Test orchestrator returns INFO status with resources_utilization_data."""
        # Verify status using base test
        RuleTestBase.test_scenario_info(self, scenario_params, tested_object)

        # Verify data payload structure
        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

            # Verify resources_utilization_data exists
            assert "resources_utilization_data" in result.extra

            # Verify data structure
            data = result.extra["resources_utilization_data"]
            assert "nodes" in data
            assert len(data["nodes"]) > 0  # At least one node

            # Verify node data structure
            for node in data["nodes"]:
                self._assert_required_fields(node, ["name", "roles", "schedulable", "core_resources"], "node data")

                # Verify core resources exist
                core = node["core_resources"]
                self._assert_required_fields(core, ["cpu", "memory"], "core resources")

                # Verify resource structure
                for resource_name, resource_info in core.items():
                    self._assert_required_fields(resource_info, ["capacity", "allocatable"], resource_name)

                    # Verify allocation info (requests/limits)
                    for allocation_type in ["requests", "limits"]:
                        if allocation_type in resource_info:
                            allocation_info = resource_info[allocation_type]
                            # allocated field is always required
                            self._assert_required_fields(allocation_info, ["allocated"], f"{resource_name} {allocation_type}")
                            # utilization_level only required when percentage present (indicated by parentheses)
                            if "(" in allocation_info["allocated"]:
                                self._assert_required_fields(allocation_info, ["utilization_level"], f"{resource_name} {allocation_type} (with percentage)")


class TestCoreResourceMatching:
    """Test core resource pattern matching."""

    def test_is_core_resource_exact_match(self):
        """Test exact string matches in CORE_RESOURCES."""
        rule = ResourcesUtilization(host_executor=None)

        assert rule._is_core_resource("cpu") is True
        assert rule._is_core_resource("memory") is True
        assert rule._is_core_resource("ephemeral-storage") is True

    def test_is_core_resource_regex_hugepages(self):
        """Test regex pattern matching for hugepages resources."""
        rule = ResourcesUtilization(host_executor=None)

        assert rule._is_core_resource("hugepages-1Gi") is True
        assert rule._is_core_resource("hugepages-2Mi") is True
        assert rule._is_core_resource("hugepages-1024Ki") is True
        assert rule._is_core_resource("hugepages-64Ki") is True

    def test_is_core_resource_extended(self):
        """Test non-core resources return False."""
        rule = ResourcesUtilization(host_executor=None)

        assert rule._is_core_resource("nvidia.com/gpu") is False
        assert rule._is_core_resource("intel.com/qat") is False
        assert rule._is_core_resource("amd.com/gpu") is False
        assert rule._is_core_resource("custom-resource") is False


class TestUtilizationLevel:
    """Test utilization level categorization."""

    def test_get_utilization_level(self):
        """Test utilization level based on percentage thresholds."""
        rule = ResourcesUtilization(host_executor=None)

        # Low utilization (< 50%)
        assert rule._get_utilization_level("0%") == "low"
        assert rule._get_utilization_level("25.5%") == "low"
        assert rule._get_utilization_level("49.9%") == "low"

        # Medium utilization (50-74%)
        assert rule._get_utilization_level("50.0%") == "medium"
        assert rule._get_utilization_level("62.3%") == "medium"
        assert rule._get_utilization_level("74.9%") == "medium"

        # High utilization (>= 75%)
        assert rule._get_utilization_level("75.0%") == "high"
        assert rule._get_utilization_level("92.1%") == "high"
        assert rule._get_utilization_level("100.0%") == "high"
        assert rule._get_utilization_level("150.0%") == "high"  # Overcommitted

    def test_get_utilization_level_invalid(self):
        """Test handling of invalid percentage strings."""
        rule = ResourcesUtilization(host_executor=None)

        assert rule._get_utilization_level("invalid") == "unknown"
        assert rule._get_utilization_level("") == "unknown"
