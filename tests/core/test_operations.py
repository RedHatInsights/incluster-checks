"""Tests for operations.py - Operator and FlowsOperator classes."""

from unittest.mock import Mock

import pytest

from openshift_in_cluster_checks.core.operations import FlowsOperator, Operator
from openshift_in_cluster_checks import global_config
from openshift_in_cluster_checks.utils.enums import Objectives


class TestOperator:
    """Test base Operator class."""

    def test_operator_init(self):
        """Test Operator initialization."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"

        operator = Operator(mock_executor)

        assert operator.get_host_ip() == "192.168.1.10"
        assert operator.get_host_name() == "test-node"

    def test_run_cmd(self):
        """Test run_cmd delegates to executor."""
        mock_executor = Mock()
        mock_executor.execute_cmd.return_value = (0, "output", "")

        operator = Operator(mock_executor)
        ret, out, err = operator.run_cmd("test command")

        assert ret == 0
        assert out == "output"
        mock_executor.execute_cmd.assert_called_once_with("test command", 120, add_bash_timeout=False)


class DummyValidator(FlowsOperator):
    """Dummy validator for testing."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "test_validator"
    title = "Test Rule"


class TestFlowsOperator:
    """Test FlowsOperator class."""

    def test_flows_operator_init(self):
        """Test FlowsOperator initialization."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []

        validator = DummyValidator(mock_executor)

        assert validator.get_unique_name() == "test_validator"
        assert validator.title == "Test Rule"

    def test_run_cmd_normal_mode(self):
        """Test run_cmd in normal mode (no debug)."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "output", "")

        # Ensure debug mode is OFF
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = False

        try:
            validator = DummyValidator(mock_executor)
            ret, out, err = validator.run_cmd("test command")

            assert ret == 0
            assert out == "output"
            assert "test command" in validator.get_bash_cmd_lines()
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_run_cmd_debug_mode(self, capsys):
        """Test run_cmd in debug mode prints command details."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (1, "stdout_output", "stderr_output")

        # Enable debug mode
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = True

        try:
            validator = DummyValidator(mock_executor)
            ret, out, err = validator.run_cmd("test command")

            # Check return values
            assert ret == 1
            assert out == "stdout_output"
            assert err == "stderr_output"

            # Check debug output was printed
            captured = capsys.readouterr()
            assert "[DEBUG] Executing on test-node: test command" in captured.out
            assert "[DEBUG] Return code: 1" in captured.out
            assert "[DEBUG] STDOUT:" in captured.out
            assert "stdout_output" in captured.out
            assert "[DEBUG] STDERR:" in captured.out
            assert "stderr_output" in captured.out
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_success(self):
        """Test get_output_from_run_cmd with successful command."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.get_output_from_run_cmd.return_value = "command output"

        # Ensure debug mode is OFF
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = False

        try:
            validator = DummyValidator(mock_executor)
            output = validator.get_output_from_run_cmd("test command")

            assert output == "command output"
            assert "test command" in validator.get_bash_cmd_lines()
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_debug_mode(self, capsys):
        """Test get_output_from_run_cmd in debug mode."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.get_output_from_run_cmd.return_value = "command output"

        # Enable debug mode
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = True

        try:
            validator = DummyValidator(mock_executor)
            output = validator.get_output_from_run_cmd("test command")

            assert output == "command output"

            # Check debug output
            captured = capsys.readouterr()
            assert "[DEBUG] Executing on test-node: test command" in captured.out
            assert "[DEBUG] Return code: 0" in captured.out
            assert "[DEBUG] STDOUT:" in captured.out
            assert "command output" in captured.out
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_failure_debug_mode(self, capsys):
        """Test get_output_from_run_cmd failure in debug mode."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.get_output_from_run_cmd.side_effect = Exception("Command failed")

        # Enable debug mode
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = True

        try:
            validator = DummyValidator(mock_executor)

            with pytest.raises(Exception, match="Command failed"):
                validator.get_output_from_run_cmd("test command")

            # Check debug output
            captured = capsys.readouterr()
            assert "[DEBUG] Executing on test-node: test command" in captured.out
            assert "[DEBUG] Command failed with exception:" in captured.out
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_add_to_rule_log(self):
        """Test adding entries to validation log."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []

        validator = DummyValidator(mock_executor)
        validator.add_to_rule_log("Test log entry")

        assert "Test log entry" in validator.get_rule_log()

    def test_run_cmd_return_is_successful(self):
        """Test run_cmd_return_is_successful returns True for exit code 0."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "success", "")

        # Ensure debug mode is OFF
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = False

        try:
            validator = DummyValidator(mock_executor)
            result = validator.run_cmd_return_is_successful("test command")

            assert result is True
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_run_cmd_return_is_successful_failure(self):
        """Test run_cmd_return_is_successful returns False for non-zero exit."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (1, "", "error")

        # Ensure debug mode is OFF
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = False

        try:
            validator = DummyValidator(mock_executor)
            result = validator.run_cmd_return_is_successful("test command")

            assert result is False
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_run_and_get_the_nth_field(self):
        """Test run_and_get_the_nth_field extracts fields correctly."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.get_output_from_run_cmd.return_value = "field1 field2 field3"

        # Ensure debug mode is OFF
        original_debug = global_config.config.debug_rule_flag
        global_config.config.debug_rule_flag = False

        try:
            validator = DummyValidator(mock_executor)
            result = validator.run_and_get_the_nth_field("test command", 2)

            assert result == "field2"
        finally:
            global_config.config.debug_rule_flag = original_debug

    def test_get_the_nth_field_static(self):
        """Test _get_the_nth_field static method."""
        from openshift_in_cluster_checks.core.operations import Operator

        # Test with default whitespace separator
        result = Operator._get_the_nth_field("one two three", 2)
        assert result == "two"

        # Test with custom separator
        result = Operator._get_the_nth_field("one,two,three", 3, separator=",")
        assert result == "three"

    def test_get_the_nth_field_out_of_bounds(self):
        """Test _get_the_nth_field raises IndexError for invalid field."""
        from openshift_in_cluster_checks.core.operations import Operator

        with pytest.raises(IndexError, match="Field 5 not found"):
            Operator._get_the_nth_field("one two three", 5)
