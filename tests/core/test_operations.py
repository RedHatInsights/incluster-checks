"""Tests for operations.py - Operator class."""

from unittest.mock import Mock

import pytest

from in_cluster_checks import global_config
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import Operator
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DummyOperator(Operator):
    """Dummy operator for testing."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "test_operator"
    title = "Test Operator"


class TestOperator:
    """Test Operator class."""

    def test_operator_init(self):
        """Test Operator initialization."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []

        operator = DummyOperator(mock_executor)

        assert operator.get_unique_name() == "test_operator"
        assert operator.title == "Test Operator"
        assert operator.get_host_ip() == "192.168.1.10"
        assert operator.get_host_name() == "test-node"

    def test_run_cmd_normal_mode(self):
        """Test run_cmd in normal mode (no debug)."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "output", "")

        # Ensure debug mode is OFF
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = False

        try:
            operator = DummyOperator(mock_executor)
            ret, out, err = operator.run_cmd(SafeCmdString("test command"))

            assert ret == 0
            assert out == "output"
            assert "test command" in operator.get_bash_cmd_lines()
        finally:
            global_config.debug_rule_flag = original_debug

    def test_run_cmd_debug_mode(self, capsys):
        """Test run_cmd in debug mode prints command details."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (1, "stdout_output", "stderr_output")

        # Enable debug mode
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = True

        try:
            operator = DummyOperator(mock_executor)
            ret, out, err = operator.run_cmd(SafeCmdString("test command"))

            # Check return values
            assert ret == 1
            assert out == "stdout_output"
            assert err == "stderr_output"

            # Check debug output was printed
            captured = capsys.readouterr()
            assert "[DEBUG] [test-node] Executing: test command" in captured.out
            assert "[DEBUG] [test-node] Return code: 1" in captured.out
            assert "[DEBUG] [test-node] STDOUT:" in captured.out
            assert "stdout_output" in captured.out
            assert "[DEBUG] [test-node] STDERR:" in captured.out
            assert "stderr_output" in captured.out
        finally:
            global_config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_success(self):
        """Test get_output_from_run_cmd with successful command."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "command output", "")

        # Ensure debug mode is OFF
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = False

        try:
            operator = DummyOperator(mock_executor)
            output = operator.get_output_from_run_cmd(SafeCmdString("test command"))

            assert output == "command output"
            assert "test command" in operator.get_bash_cmd_lines()
        finally:
            global_config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_debug_mode(self, capsys):
        """Test get_output_from_run_cmd in debug mode."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "command output", "")

        # Enable debug mode
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = True

        try:
            operator = DummyOperator(mock_executor)
            output = operator.get_output_from_run_cmd(SafeCmdString("test command"))

            assert output == "command output"

            # Check debug output
            captured = capsys.readouterr()
            assert "[DEBUG] [test-node] Executing: test command" in captured.out
            assert "[DEBUG] [test-node] Return code: 0" in captured.out
            assert "[DEBUG] [test-node] STDOUT:" in captured.out
            assert "command output" in captured.out
        finally:
            global_config.debug_rule_flag = original_debug

    def test_get_output_from_run_cmd_failure_debug_mode(self, capsys):
        """Test get_output_from_run_cmd failure in debug mode."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (1, "output", "error")

        # Enable debug mode
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = True

        try:
            operator = DummyOperator(mock_executor)

            with pytest.raises(UnExpectedSystemOutput, match="Unexpected output"):
                operator.get_output_from_run_cmd("test command")

            # Check debug output (comes from run_cmd which is called internally)
            captured = capsys.readouterr()
            assert "[DEBUG] [test-node] Executing: test command" in captured.out
            assert "[DEBUG] [test-node] Return code: 1" in captured.out
        finally:
            global_config.debug_rule_flag = original_debug

    def test_add_to_rule_log(self):
        """Test adding entries to validation log."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []

        operator = DummyOperator(mock_executor)
        operator.add_to_rule_log("Test log entry")

        assert "Test log entry" in operator.get_rule_log()

    def test_run_cmd_return_is_successful(self):
        """Test run_cmd_return_is_successful returns True for exit code 0."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "success", "")

        # Ensure debug mode is OFF
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = False

        try:
            operator = DummyOperator(mock_executor)
            result = operator.run_cmd_return_is_successful(SafeCmdString("test command"))

            assert result is True
        finally:
            global_config.debug_rule_flag = original_debug

    def test_run_cmd_return_is_successful_failure(self):
        """Test run_cmd_return_is_successful returns False for non-zero exit."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (1, "", "error")

        # Ensure debug mode is OFF
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = False

        try:
            operator = DummyOperator(mock_executor)
            result = operator.run_cmd_return_is_successful(SafeCmdString("test command"))

            assert result is False
        finally:
            global_config.debug_rule_flag = original_debug

    def test_run_and_get_the_nth_field(self):
        """Test run_and_get_the_nth_field extracts fields correctly."""
        mock_executor = Mock()
        mock_executor.ip = "192.168.1.10"
        mock_executor.host_name = "test-node"
        mock_executor.roles = []
        mock_executor.execute_cmd.return_value = (0, "field1 field2 field3", "")

        # Ensure debug mode is OFF
        original_debug = global_config.debug_rule_flag
        global_config.debug_rule_flag = False

        try:
            operator = DummyOperator(mock_executor)
            result = operator.run_and_get_the_nth_field(SafeCmdString("test command"), 2)

            assert result == "field2"
        finally:
            global_config.debug_rule_flag = original_debug

    def test_get_the_nth_field_static(self):
        """Test _get_the_nth_field static method."""
        from in_cluster_checks.core.operations import Operator

        # Test with default whitespace separator
        result = Operator._get_the_nth_field("one two three", 2)
        assert result == "two"

        # Test with custom separator
        result = Operator._get_the_nth_field("one,two,three", 3, separator=",")
        assert result == "three"

    def test_get_the_nth_field_out_of_bounds(self):
        """Test _get_the_nth_field raises IndexError for invalid field."""
        from in_cluster_checks.core.operations import Operator

        with pytest.raises(IndexError, match="Field 5 not found"):
            Operator._get_the_nth_field("one two three", 5)


class TestOperatorCachedPool:
    """Test hosts_cached_pool caching in Operator."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        global_config.debug_rule_flag = False
        self.mock_executor = Mock()
        self.mock_executor.ip = "192.168.1.10"
        self.mock_executor.host_name = "test-node"
        self.mock_executor.roles = []
        self.mock_executor.execute_cmd.return_value = (0, "output", "")
        self.operator = DummyOperator(self.mock_executor)

    def test_run_cmd_without_pool_executes_normally(self):
        """run_cmd without hosts_cached_pool executes every time."""
        self.operator.run_cmd(SafeCmdString("echo hello"))
        self.operator.run_cmd(SafeCmdString("echo hello"))

        assert self.mock_executor.execute_cmd.call_count == 2

    def test_run_cmd_with_pool_caches_result(self):
        """run_cmd with hosts_cached_pool caches and reuses result."""
        pool = {}
        self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)
        self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)

        assert self.mock_executor.execute_cmd.call_count == 1

    def test_cached_pool_returns_same_result(self):
        """Cached result matches the original execution result."""
        pool = {}
        ret1 = self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)
        ret2 = self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)

        assert ret1 == ret2
        assert ret1 == (0, "output", "")

    def test_different_commands_not_cached_together(self):
        """Different commands are cached separately."""
        self.mock_executor.execute_cmd.side_effect = [
            (0, "output_a", ""),
            (0, "output_b", ""),
        ]

        pool = {}
        ret_a = self.operator.run_cmd(SafeCmdString("cmd_a"), hosts_cached_pool=pool)
        ret_b = self.operator.run_cmd(SafeCmdString("cmd_b"), hosts_cached_pool=pool)

        assert self.mock_executor.execute_cmd.call_count == 2
        assert ret_a[1] == "output_a"
        assert ret_b[1] == "output_b"

    def test_different_hosts_not_cached_together(self):
        """Same command on different hosts is cached separately."""
        mock_executor_2 = Mock()
        mock_executor_2.ip = "192.168.1.11"
        mock_executor_2.host_name = "test-node-2"
        mock_executor_2.roles = []
        mock_executor_2.execute_cmd.return_value = (0, "output_node2", "")

        operator_2 = DummyOperator(mock_executor_2)

        pool = {}
        ret1 = self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)
        ret2 = operator_2.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)

        assert self.mock_executor.execute_cmd.call_count == 1
        assert mock_executor_2.execute_cmd.call_count == 1
        assert ret1[1] == "output"
        assert ret2[1] == "output_node2"

    def test_pool_clear_allows_re_execution(self):
        """Clearing the pool dict allows commands to be re-executed."""
        pool = {}
        self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)
        pool.clear()
        self.operator.run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)

        assert self.mock_executor.execute_cmd.call_count == 2

    def test_get_output_from_run_cmd_with_pool(self):
        """get_output_from_run_cmd propagates hosts_cached_pool."""
        pool = {}
        out1 = self.operator.get_output_from_run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)
        out2 = self.operator.get_output_from_run_cmd(SafeCmdString("echo hello"), hosts_cached_pool=pool)

        assert self.mock_executor.execute_cmd.call_count == 1
        assert out1 == out2 == "output"

    def test_get_output_from_run_cmd_pool_raises_on_failure(self):
        """get_output_from_run_cmd with pool still raises on non-zero exit."""
        self.mock_executor.execute_cmd.return_value = (1, "", "error")

        pool = {}
        with pytest.raises(UnExpectedSystemOutput):
            self.operator.get_output_from_run_cmd(SafeCmdString("bad cmd"), hosts_cached_pool=pool)
