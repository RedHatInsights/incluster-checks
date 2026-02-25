"""
Tests for InClusterCheckRunner.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from openshift_in_cluster_checks.runner import InClusterCheckRunner


class TestInClusterCheckRunner:
    """Test InClusterCheckRunner."""

    def test_runner_initialization(self):
        """Test that runner initializes correctly."""
        runner = InClusterCheckRunner()

        assert runner.logger is not None
        assert runner.factory is None
        assert runner.node_executors is None

    def test_discover_domains(self):
        """Test domain discovery."""
        from openshift_in_cluster_checks.core.domain import RuleDomain

        # Create a mock domain class
        class MockDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return []

        # Mock the module with our domain
        mock_module = Mock()
        mock_module.MockDomain = MockDomain
        setattr(mock_module, 'MockDomain', MockDomain)
        mock_module.__path__ = ['/fake/path']

        with patch('openshift_in_cluster_checks.runner.pkgutil.iter_modules', return_value=[(None, 'test_module', False)]):
            with patch('openshift_in_cluster_checks.runner.importlib.import_module', return_value=mock_module):
                with patch('builtins.dir', return_value=['MockDomain']):
                    runner = InClusterCheckRunner()
                    domains = runner.discover_domains()

        assert isinstance(domains, dict)
        assert 'test_domain' in domains


    def test_build_component_map(self):
        """Test component map building."""
        from openshift_in_cluster_checks.core.rule import Rule
        from openshift_in_cluster_checks.utils.enums import Objectives

        # Create a mock rule class
        class MockRule(Rule):
            unique_name = "test_rule"
            objective_hosts = [Objectives.ALL_NODES]

            def run_rule(self):
                pass

        # Create a mock domain
        mock_domain = Mock()
        mock_domain.get_rule_classes.return_value = [MockRule]

        domains = {"test_domain": mock_domain}

        runner = InClusterCheckRunner()
        component_map = runner.build_component_map(domains)

        assert "test_rule" in component_map
        assert MockRule.__module__ in component_map["test_rule"]
        assert "MockRule" in component_map["test_rule"]

    def test_log_summary(self):
        """Test summary logging."""
        from openshift_in_cluster_checks.utils.enums import Status

        reports = [
            {"status": Status.PASSED.value},
            {"status": Status.FAILED.value},
            {"status": Status.WARNING.value},
            {"status": Status.SKIP.value},
            {"status": Status.NOT_APPLICABLE.value},
        ]

        runner = InClusterCheckRunner()
        # Should not raise any exceptions
        runner.log_summary(reports)

    @patch('openshift_in_cluster_checks.runner.NodeExecutorFactory')
    @patch('openshift_in_cluster_checks.runner.StructedPrinter')
    @patch.object(InClusterCheckRunner, 'discover_domains')
    @patch.object(InClusterCheckRunner, 'build_component_map')
    def test_run_complete_workflow(
        self,
        mock_build_map,
        mock_discover,
        mock_printer,
        mock_factory_class
    ):
        """Test complete run workflow."""

        # Mock domain
        mock_domain = Mock()
        mock_domain.verify.return_value = {
            "domain_name": "test_domain",
            "details": {}
        }

        mock_domain_class = Mock(return_value=mock_domain)
        mock_discover.return_value = {"test_domain": mock_domain_class}

        mock_build_map.return_value = {}

        # Mock factory
        mock_factory = Mock()
        mock_factory.build_host_executors.return_value = {}
        mock_factory_class.return_value = mock_factory

        # Mock printer
        mock_printer.format_results.return_value = []

        # Run
        runner = InClusterCheckRunner()
        output_path_str = runner.run(output_path=Path("/tmp/test.json"))

        # Verify
        assert output_path_str is not None
        assert output_path_str == "/tmp/test.json"
        mock_factory.connect_all.assert_called_once()
        mock_factory.disconnect_all.assert_called_once()
        mock_domain.verify.assert_called_once()

    @patch('openshift_in_cluster_checks.runner.NodeExecutorFactory')
    @patch.object(InClusterCheckRunner, 'discover_domains')
    @patch.object(InClusterCheckRunner, 'build_component_map')
    def test_run_ensures_cleanup_on_exception(
        self,
        mock_build_map,
        mock_discover,
        mock_factory_class
    ):
        """Test that cleanup happens even if exception occurs."""

        mock_build_map.return_value = {}

        # Mock domain that raises exception
        mock_domain = Mock()
        mock_domain.verify.side_effect = Exception("Test error")
        mock_domain_class = Mock(return_value=mock_domain)
        mock_discover.return_value = {"test_domain": mock_domain_class}

        # Mock factory
        mock_factory = Mock()
        mock_factory.build_host_executors.return_value = {}
        mock_factory_class.return_value = mock_factory

        # Run and expect exception
        runner = InClusterCheckRunner()
        with pytest.raises(Exception, match="Test error"):
            runner.run(output_path=Path("/tmp/test.json"))

        # Verify cleanup still happened
        mock_factory.disconnect_all.assert_called_once()
