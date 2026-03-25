"""
Base classes for testing Pendrive in_cluster_check operators.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/pytest_tools/operator/test_operator.py
Simplified for Pendrive architecture.
"""

from typing import Dict, Any, List
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.executor import _add_bash_timeout
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class CmdOutput:
    """Mock command output for testing."""

    def __init__(self, out: str, return_code: int = 0, err: str = ""):
        """
        Initialize command output.

        Args:
            out: Standard output
            return_code: Exit code (0 for success)
            err: Standard error
        """
        self.out = out
        self.return_code = return_code
        self.err = err


class ScenarioParams:
    """Base parameters for test scenarios."""

    def __init__(
        self,
        scenario_title: str,
        cmd_input_output_dict: Dict[str, CmdOutput] = None,
        rsh_cmd_output_dict: Dict[tuple, CmdOutput] = None,
        oc_cmd_output_dict: Dict[tuple, CmdOutput] = None,
        data_collector_dict: Dict[type, Any] = None,
        library_mocks_dict: Dict[str, Mock] = None,
        tested_object_mock_dict: Dict[str, Mock] = None,
    ):
        """
        Initialize scenario parameters.

        Args:
            scenario_title: Description of the test scenario
            cmd_input_output_dict: Map of {command: CmdOutput} for run_cmd()
            rsh_cmd_output_dict: Map of {(namespace, pod, command): CmdOutput} for run_rsh_cmd()
                Example: {("openshift-ovn-kubernetes", "ovnkube-node-abc", "ovn-nbctl ls-list"): CmdOutput(...)}
            oc_cmd_output_dict: Map of {(command, tuple(args)): CmdOutput} for run_oc_command()
                Example: {("get", ("pv", "-o", "json")): CmdOutput(...)}
            data_collector_dict: Map of {DataCollectorClass: expected_result}
            library_mocks_dict: Map of {module_path: Mock} for mocking library/module functions
                Example: {"openshift_client.oc.selector": Mock(return_value=...)}
            tested_object_mock_dict: Map of {method_name: Mock} for mocking tested object methods
                Example: {"get_ovn_pod_to_node_dict": Mock(return_value={...})}
        """
        self.scenario_title = scenario_title
        self.cmd_input_output_dict = cmd_input_output_dict or {}
        self.rsh_cmd_output_dict = rsh_cmd_output_dict or {}
        self.oc_cmd_output_dict = oc_cmd_output_dict or {}
        self.data_collector_dict = data_collector_dict or {}
        self.library_mocks_dict = library_mocks_dict or {}
        self.tested_object_mock_dict = tested_object_mock_dict or {}


class OperatorTestBase:
    """
    Base class for testing Operators (Validators, DataCollectors).

    Provides mocking infrastructure for command execution and data collection.
    """

    tested_type = None  # Set by subclass to the validator/collector class

    @pytest.fixture
    def tested_object(self):
        """
        Create a tested object with mocked executor.
        Returns:
            Instance of tested_type with mocked host_executor
        """
        assert self.tested_type, "Please set tested_type in test class"
        # Clear any cached command outputs from previous tests
        # (HwFwDataCollector uses class-level cache that persists across tests)
        if hasattr(self.tested_type, 'clear_cache'):
            self.tested_type.clear_cache()

        # Create mock executor for all rules
        mock_executor = Mock()
        mock_executor.node_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
    
        # Check if this is an OrchestratorRule (doesn't need host_executor)
        if issubclass(self.tested_type, OrchestratorRule):
            # OrchestratorRule requires host_executor and optional node_executors
            tested_obj = self.tested_type(host_executor=mock_executor, node_executors=None)
        else:
            # Regular Rule requires host_executor
            tested_obj = self.tested_type(mock_executor)

        return tested_obj

    def _init_operator_object(self, operator_object, scenario_params: ScenarioParams):
        """
        Initialize operator with mocked command execution.

        Args:
            operator_object: Rule or DataCollector instance
            scenario_params: Test scenario parameters
        """
        self.cmd_to_output_dict = scenario_params.cmd_input_output_dict
        self.rsh_cmd_to_output_dict = scenario_params.rsh_cmd_output_dict
        self.oc_cmd_to_output_dict = scenario_params.oc_cmd_output_dict
        self.data_collectors = scenario_params.data_collector_dict
        self.operator_object = operator_object

        # Store mock dictionaries in instance variables (like healthcheck pattern)
        if scenario_params.library_mocks_dict is not None:
            self.library_mocks_dict = scenario_params.library_mocks_dict
        else:
            self.library_mocks_dict = {}

        if scenario_params.tested_object_mock_dict is not None:
            self.tested_object_mock_dict = scenario_params.tested_object_mock_dict
        else:
            self.tested_object_mock_dict = {}

        # Mock run_cmd to return our test data
        operator_object.run_cmd = Mock(side_effect=self._run_cmd_side_effects)

        # Mock get_output_from_run_cmd
        operator_object.get_output_from_run_cmd = Mock(
            side_effect=self._get_output_from_run_cmd_side_effects
        )

        # Mock run_rsh_cmd for OrchestratorRules
        if hasattr(operator_object, 'run_rsh_cmd'):
            operator_object.run_rsh_cmd = Mock(side_effect=self._run_rsh_cmd_side_effects)

        # Mock run_oc_command for OrchestratorRules
        if hasattr(operator_object, 'run_oc_command'):
            operator_object.run_oc_command = Mock(side_effect=self._run_oc_command_side_effects)

        # Mock run_data_collector
        operator_object.run_data_collector = Mock(
            side_effect=self._run_data_collector_side_effects
        )

        # Initialize base mocks (like healthcheck pattern)
        self._init_base_mocks(operator_object)

    def _init_base_mocks(self, operator_object):
        """
        Initialize base mocks from tested_object_mock_dict.

        Args:
            operator_object: Rule or DataCollector instance
        """
        # Apply tested_object_mock_dict - mock methods on the tested object itself
        for tested_object_method, mock_object in self.tested_object_mock_dict.items():
            setattr(operator_object, tested_object_method, mock_object)

    def _prepare_patches_list(self, scenario_params: ScenarioParams, tested_object=None) -> List:
        """
        Prepare list of mock patches from library_mocks_dict.

        Args:
            scenario_params: Test scenario parameters
            tested_object: The tested object (used to get module path for relative imports)

        Returns:
            List of patch objects to be used as context managers
        """
        patches = []
        for object_module, mock_obj in scenario_params.library_mocks_dict.items():
            # Prepend tested object's module path (like healthcheck-backup pattern)
            if tested_object is not None:
                full_module = tested_object.__module__ + "." + object_module
            else:
                full_module = object_module
            patches.append(patch(full_module, mock_obj))
        return patches

    def _run_cmd_side_effects(self, cmd: str, timeout: int = 120, add_bash_timeout: bool = False):
        """
        Mock side effect for run_cmd().

        Args:
            cmd: Command to execute
            timeout: Timeout (ignored in mock)
            add_bash_timeout: If True, wraps command with timeout before lookup

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        # Enforce SafeCmdString type to match production execute_cmd() behavior
        if not isinstance(cmd, SafeCmdString):
            raise TypeError(
                f"run_cmd() requires SafeCmdString, got {type(cmd).__name__}.\n"
                f"Use: SafeCmdString('your command') or SafeCmdString('cmd {{var}}').format(var=value)"
            )

        # Convert SafeCmdString to str first
        cmd_str = str(cmd)

        # Apply bash timeout wrapper if requested
        if add_bash_timeout:
            cmd_str = _add_bash_timeout(cmd_str, timeout)

        assert cmd_str in self.cmd_to_output_dict, (
            f"Command '{cmd_str}' not mocked. "
            f"Please add it to cmd_input_output_dict in test scenario."
        )

        res = self.cmd_to_output_dict[cmd_str]
        return res.return_code, res.out, res.err

    def _run_rsh_cmd_side_effects(self, namespace: str, pod: str, command: str, timeout: int = 120):
        """
        Mock side effect for run_rsh_cmd().

        Args:
            namespace: Namespace where pod is located
            pod: Pod name
            command: Command to execute in pod
            timeout: Timeout (ignored in mock)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        if not isinstance(command, SafeCmdString):
            raise TypeError(
                f"run_rsh_cmd() requires SafeCmdString, got {type(command).__name__}.\n"
                f"Use: SafeCmdString('your command') or SafeCmdString('cmd {{var}}').format(var=value)"
            )
        # Convert SafeCmdString to str for dictionary lookup
        command_str = str(command)
        key = (namespace, pod, command_str)

        assert key in self.rsh_cmd_to_output_dict, (
            f"RSH command {key} not mocked. "
            f"Please add it to rsh_cmd_output_dict in test scenario."
        )

        res = self.rsh_cmd_to_output_dict[key]
        return res.return_code, res.out, res.err

    def _run_oc_command_side_effects(self, command: str, args: list, timeout: int = 120, raise_on_error: bool = True):
        """
        Mock side effect for run_oc_command().

        Args:
            command: oc command (e.g., "get")
            args: List of command arguments (e.g., ["pv", "-o", "json"])
            timeout: Timeout (ignored in mock)
            raise_on_error: Raise exception on non-zero exit

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            UnExpectedSystemOutput: If raise_on_error=True and return_code != 0
        """
        _ = timeout  # Acknowledge parameter
        key = (command, tuple(args))

        assert key in self.oc_cmd_to_output_dict, (
            f"OC command {key} not mocked. "
            f"Please add it to oc_cmd_output_dict in test scenario."
        )

        res = self.oc_cmd_to_output_dict[key]

        # Honor raise_on_error parameter
        if raise_on_error and res.return_code != 0:
            cmd_str = f"oc {command} {' '.join(args)}"
            raise UnExpectedSystemOutput(
                ip=self.operator_object.get_host_ip(),
                cmd=cmd_str,
                output=res.err if res.err else res.out,
                message=f"Command failed with return code {res.return_code}",
            )

        return res.return_code, res.out, res.err

    def _get_output_from_run_cmd_side_effects(self, cmd: str, timeout: int = 30, message: str = None):
        """
        Mock side effect for get_output_from_run_cmd().

        Args:
            cmd: Command to execute
            timeout: Timeout (ignored in mock)
            message: Optional error message (ignored in mock, for HC compatibility)

        Returns:
            Command stdout

        Raises:
            Exception: If command returns non-zero
        """
        # Enforce SafeCmdString type to match production execute_cmd() behavior
        if not isinstance(cmd, SafeCmdString):
            raise TypeError(
                f"get_output_from_run_cmd() requires SafeCmdString, got {type(cmd).__name__}.\n"
                f"Use: SafeCmdString('your command') or SafeCmdString('cmd {{var}}').format(var=value)"
            )

        return_code, out, err = self._run_cmd_side_effects(cmd, timeout)

        if return_code == 0:
            return out.strip()
        else:
            raise Exception(f"Command failed (exit code {return_code}): {cmd}")

    def _run_data_collector_side_effects(self, collector_class: type, **kwargs):
        """
        Mock side effect for run_data_collector().

        Args:
            collector_class: DataCollector class to run
            **kwargs: Arguments passed to collector

        Returns:
            Mocked collected data
        """

        assert issubclass(collector_class, DataCollector), (
            f"{collector_class} is not a DataCollector subclass"
        )

        assert collector_class in self.data_collectors, (
            f"DataCollector {collector_class.__name__} not mocked. "
            f"Please add it to data_collector_dict in test scenario."
        )

        return self.data_collectors[collector_class]
