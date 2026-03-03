"""Tests for runner.py - InClusterCheckRunner class."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks import global_config
from in_cluster_checks.runner import InClusterCheckRunner


class TestInClusterCheckRunner:
    """Test InClusterCheckRunner class."""

    def test_init_default_config(self):
        """Test runner initialization with default parameters."""
        runner = InClusterCheckRunner()

        # Verify global config was set with defaults
        assert global_config.debug_rule_flag is False
        assert global_config.debug_rule_name == ""
        assert global_config.max_workers == 50

    def test_init_custom_config(self):
        """Test runner initialization with custom parameters."""
        runner = InClusterCheckRunner(
            debug_rule_flag=True,
            debug_rule_name="TestRule",
            max_workers=75,
        )

        # Verify global config was set with custom values
        assert global_config.debug_rule_flag is True
        assert global_config.debug_rule_name == "TestRule"
        assert global_config.max_workers == 75

    @patch('in_cluster_checks.runner.NodeExecutorFactory')
    def test_run_success(self, mock_executor_factory):
        """Test successful run."""
        # Mock executor factory
        mock_factory_instance = Mock()
        mock_factory_instance.build_host_executors.return_value = []
        mock_factory_instance.connect_all.return_value = None
        mock_factory_instance.disconnect_all.return_value = None
        mock_executor_factory.return_value = mock_factory_instance

        runner = InClusterCheckRunner()
        output_path = Path("/tmp/test-results.json")

        # Mock the discover_domains to return an empty dict to avoid actual domain loading
        with patch.object(runner, 'discover_domains', return_value={}):
            # Mock StructedPrinter methods
            with patch('in_cluster_checks.runner.StructedPrinter.format_results', return_value=[]):
                with patch('in_cluster_checks.runner.StructedPrinter.print_to_json') as mock_print:
                    result = runner.run(output_path=output_path)

                    assert result == str(output_path)
                    mock_print.assert_called_once_with([], str(output_path))

    @patch('in_cluster_checks.runner.NodeExecutorFactory')
    def test_run_debug_mode_no_json(self, mock_executor_factory):
        """Test run in debug mode skips JSON output."""
        # Mock executor factory
        mock_factory_instance = Mock()
        mock_factory_instance.build_host_executors.return_value = []
        mock_factory_instance.connect_all.return_value = None
        mock_factory_instance.disconnect_all.return_value = None
        mock_executor_factory.return_value = mock_factory_instance

        # Create runner in debug mode
        runner = InClusterCheckRunner(
            debug_rule_flag=True,
            debug_rule_name="TestRule"
        )
        output_path = Path("/tmp/test-results.json")

        # Mock the discover_domains to return an empty dict
        with patch.object(runner, 'discover_domains', return_value={}):
            # Mock StructedPrinter methods
            with patch('in_cluster_checks.runner.StructedPrinter.format_results', return_value=[]):
                with patch('in_cluster_checks.runner.StructedPrinter.print_to_json') as mock_print:
                    result = runner.run(output_path=output_path)

                    # In debug mode, JSON output should NOT be called
                    mock_print.assert_not_called()
                    assert result == str(output_path)
