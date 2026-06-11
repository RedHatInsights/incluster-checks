"""Unit tests for NodeResourcesCollector."""

from unittest.mock import Mock

import pytest

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.rules.resources_utilization.resources_utilization import NodeResourcesCollector
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestNodeResourcesCollector(DataCollectorTestBase):
    """Test NodeResourcesCollector data collector."""

    tested_type = NodeResourcesCollector

    describe_output_worker = """
Allocated resources:
  Resource           Requests       Limits
  --------           --------       ------
  cpu                100m (1%)      200m (2%)
  memory             128Mi (0%)     256Mi (0%)
Events:              <none>
"""

    describe_output_master = """
Allocated resources:
  Resource           Requests       Limits
  --------           --------       ------
  cpu                550m (3%)      1000m (6%)
  memory             1Gi (1%)       2Gi (3%)
Events:              <none>
"""

    # Helper to create single node mock
    def _create_single_node_mock(node_name):
        """Create a single node mock for testing failure scenarios."""
        node = Mock()
        node.name.return_value = node_name
        node.model.spec.get.return_value = False
        capacity = Mock()
        capacity._primitive.return_value = {"cpu": "8", "memory": "32Gi"}
        allocatable = Mock()
        allocatable._primitive.return_value = {"cpu": "8", "memory": "32Gi"}
        node.model.status.capacity = capacity
        node.model.status.allocatable = allocatable
        return Mock(return_value=[node])

    # Mock node objects
    def _create_node_objects():
        # Worker node with APIObject accessors
        worker_node = Mock()
        worker_node.name.return_value = "worker-1"
        worker_node.model.spec.get.return_value = False  # unschedulable=False
        worker_capacity = Mock()
        worker_capacity._primitive.return_value = {"cpu": "8", "memory": "32Gi"}
        worker_allocatable = Mock()
        worker_allocatable._primitive.return_value = {"cpu": "8", "memory": "32Gi"}
        worker_node.model.status.capacity = worker_capacity
        worker_node.model.status.allocatable = worker_allocatable

        # Master node with APIObject accessors
        master_node = Mock()
        master_node.name.return_value = "master-1"
        master_node.model.spec.get.return_value = False  # unschedulable=False
        master_capacity = Mock()
        master_capacity._primitive.return_value = {"cpu": "16", "memory": "64Gi"}
        master_allocatable = Mock()
        master_allocatable._primitive.return_value = {"cpu": "16", "memory": "64Gi"}
        master_node.model.status.capacity = master_capacity
        master_node.model.status.allocatable = master_allocatable

        return [worker_node, master_node]

    # Mock node executors
    def _create_node_executors():
        worker_executor = Mock()
        worker_executor.node_labels = "worker"
        master_executor = Mock()
        master_executor.node_labels = "control-plane,master"
        return {
            "worker-1": worker_executor,
            "master-1": master_executor,
        }

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="collect node resources with allocated data",
            cmd_input_output_dict={},
            oc_cmd_output_dict={
                ("describe", ("node", "worker-1")): CmdOutput(describe_output_worker),
                ("describe", ("node", "master-1")): CmdOutput(describe_output_master),
            },
            tested_object_mock_dict={
                "oc_api.get_all_nodes": Mock(return_value=_create_node_objects()),
            },
            scenario_res={
                "nodes": [
                    {
                        "name": "worker-1",
                        "roles": ["worker"],
                        "schedulable": True,
                        "capacity": {"cpu": "8", "memory": "32Gi"},
                        "allocatable": {"cpu": "8", "memory": "32Gi"},
                        "allocated": {
                            "cpu": {
                                "requests": "100m",
                                "requests_percentage": "1%",
                                "limits": "200m",
                                "limits_percentage": "2%",
                            },
                            "memory": {
                                "requests": "128Mi",
                                "requests_percentage": "0%",
                                "limits": "256Mi",
                                "limits_percentage": "0%",
                            },
                        },
                    },
                    {
                        "name": "master-1",
                        "roles": ["control-plane", "master"],
                        "schedulable": True,
                        "capacity": {"cpu": "16", "memory": "64Gi"},
                        "allocatable": {"cpu": "16", "memory": "64Gi"},
                        "allocated": {
                            "cpu": {
                                "requests": "550m",
                                "requests_percentage": "3%",
                                "limits": "1000m",
                                "limits_percentage": "6%",
                            },
                            "memory": {
                                "requests": "1Gi",
                                "requests_percentage": "1%",
                                "limits": "2Gi",
                                "limits_percentage": "3%",
                            },
                        },
                    },
                ]
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="no nodes found",
            cmd_input_output_dict={},
            tested_object_mock_dict={
                "oc_api.get_all_nodes": Mock(return_value=[]),
            },
            scenario_res={"nodes": []},
        ),
    ]

    scenario_unexpected_system_output = [
        DataCollectorScenarioParams(
            scenario_title="oc describe node fails",
            cmd_input_output_dict={},
            oc_cmd_output_dict={
                ("describe", ("node", "worker-1")): CmdOutput(
                    "Error: node not found", return_code=1
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_all_nodes": _create_single_node_mock("worker-1"),
                "oc_api.run_oc_command": Mock(
                    side_effect=UnExpectedSystemOutput(
                        ip="test", cmd="oc describe node worker-1", output="Error: node not found"
                    )
                ),
            },
            scenario_res=None,
        ),
        DataCollectorScenarioParams(
            scenario_title="get_all_nodes fails",
            cmd_input_output_dict={},
            tested_object_mock_dict={
                "oc_api.get_all_nodes": Mock(
                    side_effect=UnExpectedSystemOutput(
                        ip="test", cmd="oc get nodes", output="Error: unable to connect to cluster"
                    )
                ),
            },
            scenario_res=None,
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NodeResourcesCollector collect_data() with node_executors."""
        self._init_data_collector_object(tested_object, scenario_params)

        # Pass node_executors to match real runtime behavior (orchestrator passes it)
        node_executors = self._get_node_executors(scenario_params)
        result = tested_object.collect_data(node_executors=node_executors)

        assert result == scenario_params.scenario_res

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        """Test that data collector raises UnExpectedSystemOutput for given scenario."""
        self._init_data_collector_object(tested_object, scenario_params)

        node_executors = self._get_node_executors(scenario_params)

        # Should raise UnExpectedSystemOutput exception
        with pytest.raises(UnExpectedSystemOutput):
            tested_object.collect_data(node_executors=node_executors)

    def _get_node_executors(self, scenario_params):
        """Create node_executors dict for testing."""
        if "allocated data" in scenario_params.scenario_title:
            return TestNodeResourcesCollector._create_node_executors()
        return {}


class TestNodeResourcesCollectorParsing:
    """Test NodeResourcesCollector parsing methods."""

    @pytest.fixture
    def tested_object(self):
        """Create instance of NodeResourcesCollector for testing."""
        return NodeResourcesCollector(host_executor=Mock())

    def test_parse_allocated_resources(self, tested_object):
        """Test parsing allocated resources section from oc describe node output."""
        describe_output = """
Name:               worker-1
Roles:              worker
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests       Limits
  --------           --------       ------
  cpu                6933m (92%)    2660m (35%)
  memory             25724Mi (83%)  30212Mi (97%)
  ephemeral-storage  0 (0%)         0 (0%)
Events:              <none>
"""

        allocated = tested_object._parse_allocated_resources(describe_output)

        assert "cpu" in allocated
        assert allocated["cpu"]["requests"] == "6933m"
        assert allocated["cpu"]["limits"] == "2660m"

        assert "memory" in allocated
        assert allocated["memory"]["requests"] == "25724Mi"
        assert allocated["memory"]["limits"] == "30212Mi"

        assert "ephemeral-storage" in allocated
        assert allocated["ephemeral-storage"]["requests"] == "0"
        assert allocated["ephemeral-storage"]["limits"] == "0"

    def test_parse_resource_line(self, tested_object):
        """Test parsing individual resource lines."""
        line = "  cpu                6933m (92%)    2660m (35%)"
        result = tested_object._parse_resource_line(line)

        assert result is not None
        assert result["resource_name"] == "cpu"
        assert result["requests_value"] == "6933m"
        assert result["requests_pct"] == "92"
        assert result["limits_value"] == "2660m"
        assert result["limits_pct"] == "35"

    def test_parse_resource_line_memory(self, tested_object):
        """Test parsing memory resource line."""
        line = "  memory             25724Mi (83%)  30212Mi (97%)"
        result = tested_object._parse_resource_line(line)

        assert result is not None
        assert result["resource_name"] == "memory"
        assert result["requests_value"] == "25724Mi"
        assert result["requests_pct"] == "83"
        assert result["limits_value"] == "30212Mi"
        assert result["limits_pct"] == "97"

    def test_parse_resource_line_invalid(self, tested_object):
        """Test parsing invalid lines returns None."""
        # Comment line (doesn't match 3-word pattern)
        assert tested_object._parse_resource_line("  (Total limits may be over 100 percent, i.e., overcommitted.)") is None

        # Empty line
        assert tested_object._parse_resource_line("") is None

        # Line with only one word
        assert tested_object._parse_resource_line("  cpu") is None

    def test_parse_empty_allocated_section(self, tested_object):
        """Test parsing when no allocated resources section exists."""
        describe_output = """
Name:               worker-1
Roles:              worker
Events:              <none>
"""

        allocated = tested_object._parse_allocated_resources(describe_output)
        assert allocated == {}

    def test_extract_roles(self, tested_object):
        """Test extracting roles from node_executors."""
        # Create mock executor with roles
        executor = Mock()
        executor.node_labels = "control-plane,master,worker"
        node_executors = {"test-node": executor}

        roles = tested_object._extract_roles("test-node", node_executors)
        assert roles == ["control-plane", "master", "worker"]

    def test_extract_roles_missing_node(self, tested_object):
        """Test extracting roles when node not in executors."""
        roles = tested_object._extract_roles("missing-node", {})
        assert roles == []

    def test_extract_roles_no_labels(self, tested_object):
        """Test extracting roles when executor has no labels."""
        executor = Mock()
        executor.node_labels = None
        node_executors = {"test-node": executor}

        roles = tested_object._extract_roles("test-node", node_executors)
        assert roles == []
