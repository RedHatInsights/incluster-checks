"""Tests for runner.py - InClusterCheckRunner class."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.interfaces.config import InClusterCheckConfig
from in_cluster_checks.runner import InClusterCheckRunner


class TestInClusterCheckRunner:
    """Test InClusterCheckRunner class."""

    def test_init_default_config(self):
        """Test runner initialization with default config."""
        runner = InClusterCheckRunner()

        assert runner.config is not None
        assert isinstance(runner.config, InClusterCheckConfig)
        assert runner.config.parallel_execution is True
        assert runner.config.filter_secrets is True

    def test_init_custom_config(self):
        """Test runner initialization with custom config."""
        custom_config = InClusterCheckConfig(
            parallel_execution=False,
            max_workers=5,
            command_timeout=60,
            filter_secrets=False,
        )

        runner = InClusterCheckRunner(config=custom_config)

        assert runner.config == custom_config
        assert runner.config.parallel_execution is False
        assert runner.config.max_workers == 5

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
