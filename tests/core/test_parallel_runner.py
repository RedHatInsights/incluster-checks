"""Tests for ParallelRunner."""

import time
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.parallel_runner import ParallelRunner


class TestParallelRunner:
    """Test ParallelRunner functionality."""

    def test_run_in_parallel(self):
        """Test running validators in parallel."""
        # Create mock validators with actual name attribute
        results = []

        def mock_target_func(validator, results_list):
            """Mock function that records execution."""
            time.sleep(0.01)  # Simulate work
            results_list.append(validator.validator_name)

        validators = []
        for i in range(3):
            v = Mock()
            v.validator_name = f"validator{i}"
            validators.append(v)

        ParallelRunner.run_in_parallel(
            validators,
            mock_target_func,
            results
        )

        # All validators should have run
        assert len(results) == 3
        assert "validator0" in results
        assert "validator1" in results
        assert "validator2" in results

    def test_run_in_parallel_with_kwargs(self):
        """Test running validators with keyword arguments."""
        results = {}

        def mock_target_func(validator, results_dict, extra_param=None):
            """Mock function with kwargs."""
            results_dict[validator.validator_name] = extra_param

        validators = []
        for i in range(2):
            v = Mock()
            v.validator_name = f"validator{i}"
            validators.append(v)

        ParallelRunner.run_in_parallel(
            validators,
            mock_target_func,
            results,
            extra_param="test_value"
        )

        assert len(results) == 2
        assert results["validator0"] == "test_value"
        assert results["validator1"] == "test_value"

    def test_run_in_parallel_empty_list(self):
        """Test running with empty validator list."""
        results = []

        def mock_target_func(validator, results_list):
            results_list.append(validator.name)

        # Should not raise exception
        ParallelRunner.run_in_parallel([], mock_target_func, results)

        assert len(results) == 0

    def test_run_data_collectors_in_parallel(self):
        """Test running data collectors in parallel."""
        # Create mock collectors
        collectors = []
        for i in range(3):
            collector = Mock()
            collector.get_host_name.return_value = f"host{i}"
            collector.collect_data.return_value = {"data": f"value{i}"}
            collector.get_bash_cmd_lines.return_value = [f"cmd{i}"]
            collector.get_rule_log.return_value = [f"log{i}"]
            collectors.append(collector)

        results_dict = {}

        ParallelRunner.run_data_collectors_in_parallel(
            collectors,
            results_dict
        )

        # All collectors should have run
        assert len(results_dict) == 3
        assert results_dict["host0"]["data"] == {"data": "value0"}
        assert results_dict["host0"]["bash_cmd_lines"] == ["cmd0"]
        assert results_dict["host0"]["rule_log"] == ["log0"]
        assert results_dict["host0"]["exception"] is None

    def test_run_data_collectors_with_exception(self):
        """Test data collector exception handling."""
        # Create collector that raises exception
        collector = Mock()
        collector.get_host_name.return_value = "host1"
        collector.collect_data.side_effect = Exception("Collection failed")
        collector.get_bash_cmd_lines.return_value = []
        collector.get_rule_log.return_value = []
        collector.format_exception_for_logging.return_value = "Exception: Collection failed"

        results_dict = {}

        ParallelRunner.run_data_collectors_in_parallel(
            [collector],
            results_dict
        )

        # Should record exception
        assert "host1" in results_dict
        assert results_dict["host1"]["data"] is None
        assert results_dict["host1"]["exception"] == "Exception: Collection failed"
