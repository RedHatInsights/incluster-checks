"""
Base class for testing Validators.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/pytest_tools/operator/test_validation_base.py
"""

import re
import pytest
from contextlib import ExitStack

from openshift_in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from openshift_in_cluster_checks.utils.enums import Status
from tests.pytest_tools.test_operator_base import OperatorTestBase, ScenarioParams


class RuleScenarioParams(ScenarioParams):
    """Parameters for rule test scenarios."""

    def __init__(
        self,
        scenario_title: str,
        cmd_input_output_dict: dict = None,
        rsh_cmd_output_dict: dict = None,
        data_collector_dict: dict = None,
        library_mocks_dict: dict = None,
        tested_object_mock_dict: dict = None,
        failed_msg: str = None,
    ):
        """
        Initialize rule scenario parameters.

        Args:
            scenario_title: Description of scenario
            cmd_input_output_dict: Map of {command: CmdOutput}
            rsh_cmd_output_dict: Map of {(namespace, pod, command): CmdOutput}
            data_collector_dict: Map of {DataCollectorClass: result}
            library_mocks_dict: Map of {module_path: Mock}
            tested_object_mock_dict: Map of {method_name: Mock}
            failed_msg: Expected failure message (for failed scenarios)
        """
        super().__init__(
            scenario_title,
            cmd_input_output_dict,
            rsh_cmd_output_dict,
            data_collector_dict,
            library_mocks_dict,
            tested_object_mock_dict,
        )
        self.failed_msg = failed_msg


class RuleTestBase(OperatorTestBase):
    """
    Base class for testing Rule classes.

    Subclasses should define:
    - tested_type: The Rule class to test
    - scenario_passed: List of RuleScenarioParams for passing tests
    - scenario_failed: List of RuleScenarioParams for failing tests (FAILED status)
    - scenario_warning: List of RuleScenarioParams for warning tests (WARNING status)
    - scenario_unexpected_system_output: List of RuleScenarioParams that should raise UnExpectedSystemOutput
    """

    scenario_passed = []
    scenario_failed = []
    scenario_warning = []
    scenario_unexpected_system_output = []

    def _apply_patches(self, scenario_params, tested_object):
        """
        Apply library patches and return ExitStack context manager.

        This is the Python 3 equivalent of the nested(*context_managers) pattern
        used in healthcheck-backup.

        Args:
            scenario_params: Test scenario parameters
            tested_object: The tested object (used to get module path for relative imports)

        Returns:
            ExitStack context manager with all patches applied

        Usage:
            with self._apply_patches(scenario_params, tested_object):
                # test code here
        """
        patches = self._prepare_patches_list(scenario_params, tested_object)
        stack = ExitStack()
        for patch in patches:
            stack.enter_context(patch)
        return stack

    @staticmethod
    def _normalize_message(message: str) -> str:
        """
        Normalize message by sorting lists within it for deterministic comparison.
        
        Finds patterns like ['item1', 'item2'] and sorts them alphabetically.
        This handles cases where rules use sets internally (non-deterministic order).
        
        Args:
            message: Original message string
            
        Returns:
            Message with all lists sorted
        """
        def sort_list_match(match):
            """Sort the list found in the regex match."""
            list_str = match.group(0)
            # Extract items from the list string
            items = re.findall(r"'([^']*)'", list_str)
            # Sort and reconstruct the list
            sorted_items = sorted(items)
            return str(sorted_items)
        
        # Find all list patterns like ['item1', 'item2', ...] and sort them
        normalized = re.sub(r"\[(?:'[^']*'(?:,\s*)?)+\]", sort_list_match, message)
        return normalized

    def _assert_message_match(self, actual_message: str, expected_message: str):
        """
        Assert that actual and expected messages match after normalization.
        
        Normalizes both messages to handle non-deterministic list ordering.
        
        Args:
            actual_message: The actual message from the rule
            expected_message: The expected message from test scenario
        
        Raises:
            AssertionError: If messages don't match after normalization
        """
        normalized_actual = self._normalize_message(actual_message)
        normalized_expected = self._normalize_message(expected_message)
        assert normalized_actual == normalized_expected, (
            f"Expected exact message match.\n"
            f"Expected:\n{expected_message}\n"
            f"Actual:\n{actual_message}"
        )

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """
        Test that prerequisite check returns not fulfilled.

        Args:
            scenario_params: RuleScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.check_prerequisite()
            assert result.fulfilled is False, (
                f"Prerequisite should not be fulfilled for scenario: {scenario_params.scenario_title}"
            )

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """
        Test that prerequisite check returns fulfilled.

        Args:
            scenario_params: RuleScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.check_prerequisite()
            assert result.fulfilled is True, (
                f"Prerequisite should be fulfilled for scenario: {scenario_params.scenario_title}"
            )

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        """
        Test that validator passes for given scenario.

        Args:
            scenario_params: ValidationScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            assert tested_object.run_rule(), (
                f"Rule should pass for scenario: {scenario_params.scenario_title}"
            )

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        """
        Test that validator fails (FAILED status) for given scenario.

        Args:
            scenario_params: RuleScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()
            assert not result, (
                f"Rule should fail for scenario: {scenario_params.scenario_title}"
            )

            # Should be FAILED status
            assert result.status == Status.FAILED, (
                f"Expected FAILED status, got {result.status} for scenario: {scenario_params.scenario_title}"
            )

            # Check failure message if specified
            if scenario_params.failed_msg is not None:
                self._assert_message_match(result.message, scenario_params.failed_msg)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        """
        Test that validator returns warning (WARNING status) for given scenario.

        Args:
            scenario_params: RuleScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

            # Should return warning (evaluates to False in boolean context)
            assert not result, (
                f"Rule should return warning for scenario: {scenario_params.scenario_title}"
            )

            # Should be WARNING status
            assert result.status == Status.WARNING, (
                f"Expected WARNING status, got {result.status} for scenario: {scenario_params.scenario_title}"
            )

            # Check warning message if specified
            if scenario_params.failed_msg is not None:
                self._assert_message_match(result.message, scenario_params.failed_msg)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        """
        Test that validator raises UnExpectedSystemOutput for given scenario.

        Args:
            scenario_params: RuleScenarioParams with test data
            tested_object: Rule instance (from fixture)
        """
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            # Should raise UnExpectedSystemOutput exception
            with pytest.raises(UnExpectedSystemOutput):
                tested_object.run_rule()

    def _init_validation_object(self, val_object, scenario_params=None):
        """
        Initialize validator for testing.

        Args:
            val_object: Rule instance
            scenario_params: Test scenario parameters
        """
        self._init_operator_object(val_object, scenario_params)
