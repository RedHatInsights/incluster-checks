"""Tests for cli.py - Command line interface."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from in_cluster_checks.cli import (
    check_oc_available,
    list_domains,
    list_rules,
    main,
    setup_logging,
)


class TestCLI:
    """Test CLI functions."""

    def test_setup_logging_info(self):
        """Test logging setup with INFO level."""
        setup_logging("INFO")
        import logging
        logger = logging.getLogger("in_cluster_checks")
        assert logger.level == logging.INFO

    def test_setup_logging_debug(self):
        """Test logging setup with DEBUG level."""
        setup_logging("DEBUG")
        import logging
        logger = logging.getLogger("in_cluster_checks")
        assert logger.level == logging.DEBUG

    def test_check_oc_available_success(self):
        """Test oc availability check when oc is available."""
        with patch('shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/oc'
            check_oc_available()  # Should not raise

    def test_check_oc_available_failure(self):
        """Test oc availability check when oc is not available."""
        with patch('shutil.which') as mock_which:
            mock_which.return_value = None
            with pytest.raises(SystemExit) as exc_info:
                check_oc_available()
            assert exc_info.value.code == 3

    def test_list_domains(self, capsys):
        """Test list domains functionality."""
        mock_runner = Mock()
        mock_domain1 = Mock()
        mock_domain1.return_value.domain_name.return_value = "test_domain"
        mock_domain1.return_value.get_rule_classes.return_value = [Mock(), Mock()]

        mock_runner.discover_domains.return_value = {"test_domain": mock_domain1}

        with pytest.raises(SystemExit) as exc_info:
            list_domains(mock_runner)

        captured = capsys.readouterr()
        assert "test_domain" in captured.out
        assert exc_info.value.code == 0

    def test_list_rules(self, capsys):
        """Test list rules functionality."""
        mock_runner = Mock()
        mock_rule = Mock()
        mock_rule.get_unique_name_classmethod.return_value = "test_rule"
        mock_rule.get_title_classmethod.return_value = "Test Rule"

        mock_domain = Mock()
        mock_domain.return_value.domain_name.return_value = "test_domain"
        mock_domain.return_value.get_rule_classes.return_value = [mock_rule]

        mock_runner.discover_domains.return_value = {"test_domain": mock_domain}

        with pytest.raises(SystemExit) as exc_info:
            list_rules(mock_runner)

        captured = capsys.readouterr()
        assert "test_domain" in captured.out
        assert "test_rule" in captured.out
        assert exc_info.value.code == 0

    @patch('in_cluster_checks.cli.InClusterCheckRunner')
    @patch('in_cluster_checks.cli.check_oc_available')
    def test_main_basic_run(self, mock_check_oc, mock_runner_class):
        """Test main with basic run."""
        mock_runner = Mock()
        mock_runner.run.return_value = "/tmp/results.json"
        mock_runner_class.return_value = mock_runner
        
        test_args = ['openshift-checks', '--output', '/tmp/test.json']
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    @patch('in_cluster_checks.cli.check_oc_available')
    def test_main_list_domains(self, mock_check_oc, capsys):
        """Test main with --list-domains."""
        test_args = ['openshift-checks', '--list-domains']
        with patch.object(sys, 'argv', test_args):
            with patch('in_cluster_checks.cli.list_domains') as mock_list:
                mock_list.side_effect = SystemExit(0)
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
                mock_list.assert_called_once()

    @patch('in_cluster_checks.cli.check_oc_available')
    def test_main_list_rules(self, mock_check_oc, capsys):
        """Test main with --list-rules."""
        test_args = ['openshift-checks', '--list-rules']
        with patch.object(sys, 'argv', test_args):
            with patch('in_cluster_checks.cli.list_rules') as mock_list:
                mock_list.side_effect = SystemExit(0)
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0
                mock_list.assert_called_once()

    @patch('in_cluster_checks.cli.InClusterCheckRunner')
    @patch('in_cluster_checks.cli.check_oc_available')
    def test_main_with_debug_rule(self, mock_check_oc, mock_runner_class):
        """Test main with --debug-rule."""
        mock_runner = Mock()
        mock_runner.run.return_value = "/tmp/results.json"
        mock_runner_class.return_value = mock_runner
        
        test_args = ['openshift-checks', '--debug-rule', 'test_rule', '--output', '/tmp/test.json']
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
