"""
Base class for testing DataCollectors.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/pytest_tools/operator/test_data_collector.py
"""

import pytest

from tests.pytest_tools.test_operator_base import OperatorTestBase, ScenarioParams


class DataCollectorScenarioParams(ScenarioParams):
    """Parameters for data collector test scenarios."""

    def __init__(
        self,
        scenario_title: str,
        cmd_input_output_dict: dict,
        scenario_res: any,
    ):
        """
        Initialize data collector scenario parameters.

        Args:
            scenario_title: Description of scenario
            cmd_input_output_dict: Map of {command: CmdOutput}
            scenario_res: Expected result from collect_data()
        """
        super().__init__(scenario_title, cmd_input_output_dict, None)
        self.scenario_res = scenario_res


class DataCollectorTestBase(OperatorTestBase):
    """
    Base class for testing DataCollector classes.

    Subclasses should define:
    - tested_type: The DataCollector class to test
    - scenarios: List of DataCollectorScenarioParams
    """

    scenarios = []

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """
        Test that data collector returns expected data.

        Args:
            scenario_params: DataCollectorScenarioParams with test data
            tested_object: DataCollector instance (from fixture)
        """
        self._init_data_collector_object(tested_object, scenario_params)

        result = tested_object.collect_data()

        assert result == scenario_params.scenario_res, (
            f"Data collector result mismatch for scenario: {scenario_params.scenario_title}\n"
            f"Expected: {scenario_params.scenario_res}\n"
            f"Got: {result}"
        )

    def _init_data_collector_object(self, collector_object, scenario_params=None):
        """
        Initialize data collector for testing.

        Args:
            collector_object: DataCollector instance
            scenario_params: Test scenario parameters
        """
        self._init_operator_object(collector_object, scenario_params)

        # Call subclass-specific mock initialization if defined
        if hasattr(self, '_init_mocks'):
            self._init_mocks(collector_object, scenario_params)
