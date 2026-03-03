"""Tests for NodeExecutor."""

import json
import threading
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from in_cluster_checks.core.exceptions import HostNotReachable, UnExpectedSystemOutput
from in_cluster_checks.core.executor import NodeExecutor, OrchestratorExecutor
from in_cluster_checks.utils.enums import Objectives


class TestNodeExecutor:
    """Test NodeExecutor functionality."""

    @patch('in_cluster_checks.core.executor.oc')
    def test_init(self, mock_oc):
        """Test NodeExecutor initialization."""
        executor = NodeExecutor("test-node", "192.168.1.10", "default")

        assert executor.node_name == "test-node"
        assert executor.ip == "192.168.1.10"
        assert executor.host_name == "test-node"
        assert executor.namespace == "default"
        assert executor.is_local is False
        assert executor.is_connected is False
        assert executor._pod_id is None

    def test_init_without_openshift_client(self):
        """Test NodeExecutor initialization without openshift_client library."""
        with patch('in_cluster_checks.core.executor.oc', None):
            with pytest.raises(ImportError, match="openshift_client library is required"):
                NodeExecutor("test-node", "192.168.1.10")

    @patch('in_cluster_checks.core.executor.oc')
    @patch('in_cluster_checks.core.executor.atexit')
    @patch('in_cluster_checks.core.executor.time')
    def test_connect_success(self, mock_time, mock_atexit, mock_oc):
        """Test successful connection."""
        # Mock oc debug pod creation
        mock_result = Mock()
        mock_result.out.return_value = json.dumps({
            "metadata": {"name": "temp", "namespace": "default"},
            "spec": {}
        })
        mock_oc.invoke.return_value = mock_result
        mock_oc.create.return_value = None

        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.connect()

        assert executor.is_connected is True
        assert executor._pod_id is not None
        assert "test-node-debug-" in executor._pod_id
        mock_atexit.register.assert_called_once_with(executor.close_connection)

    @patch('in_cluster_checks.core.executor.oc')
    def test_connect_already_connected(self, mock_oc):
        """Test connect when already connected."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "existing-pod"

        executor.connect()

        # Should not try to create new pod
        mock_oc.invoke.assert_not_called()

    @patch('in_cluster_checks.core.executor.oc')
    @patch('in_cluster_checks.core.executor.time')
    def test_connect_failure(self, mock_time, mock_oc):
        """Test connection failure."""
        # Mock oc debug to raise exception
        mock_oc.invoke.side_effect = Exception("Connection failed")

        executor = NodeExecutor("test-node", "192.168.1.10")

        with pytest.raises(HostNotReachable, match="Cannot create oc debug pod"):
            executor.connect()

        assert executor.is_connected is False

    @patch('in_cluster_checks.core.executor.oc')
    @patch('in_cluster_checks.core.executor.time')
    def test_generate_debug_pod_creates_unique_id(self, mock_time, mock_oc):
        """Test that debug pod gets unique ID."""
        mock_result = Mock()
        mock_result.out.return_value = json.dumps({
            "metadata": {"name": "temp", "namespace": "default"},
            "spec": {}
        })
        mock_oc.invoke.return_value = mock_result

        executor1 = NodeExecutor("test-node", "192.168.1.10")
        executor2 = NodeExecutor("test-node", "192.168.1.10")

        executor1._generate_debug_pod()
        executor2._generate_debug_pod()

        # Pod IDs should be different
        assert executor1._pod_id != executor2._pod_id
        assert "test-node-debug-" in executor1._pod_id
        assert "test-node-debug-" in executor2._pod_id

    @patch('in_cluster_checks.core.executor.oc')
    def test_execute_cmd_success(self, mock_oc):
        """Test successful command execution."""
        # Setup connected executor
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        # Mock command result
        mock_result = Mock()
        mock_result.status.return_value = 0
        mock_result.out.return_value = "command output"
        mock_result.err.return_value = ""
        mock_oc.invoke.return_value = mock_result

        rc, out, err = executor.execute_cmd("echo test")

        assert rc == 0
        assert out == "command output"
        assert err == ""

    @patch('in_cluster_checks.core.executor.oc')
    @patch('in_cluster_checks.core.executor.time')
    @patch('in_cluster_checks.core.executor.atexit')
    def test_execute_cmd_auto_connect(self, mock_atexit, mock_time, mock_oc):
        """Test execute_cmd auto-connects if not connected."""
        # Mock oc debug pod creation
        mock_result = Mock()
        mock_result.out.return_value = json.dumps({
            "metadata": {"name": "temp", "namespace": "default"},
            "spec": {}
        })
        mock_result.status.return_value = 0
        mock_oc.invoke.return_value = mock_result

        executor = NodeExecutor("test-node", "192.168.1.10")

        rc, out, err = executor.execute_cmd("echo test")

        assert executor.is_connected is True

    @patch('in_cluster_checks.core.executor.oc')
    def test_execute_cmd_pod_disappeared_reconnect(self, mock_oc):
        """Test reconnect on pod-not-found error."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "old-pod"

        # Mock reconnect debug pod creation
        mock_reconnect_result = Mock()
        mock_reconnect_result.out.return_value = json.dumps({
            "metadata": {"name": "new", "namespace": "default"},
            "spec": {}
        })

        # Mock successful command after reconnect
        mock_cmd_result = Mock()
        mock_cmd_result.status.return_value = 0
        mock_cmd_result.out.return_value = "output"
        mock_cmd_result.err.return_value = ""

        # First invoke() call raises exception, second is for reconnect debug, third is retry
        call_count = [0]
        def invoke_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First rsh command fails with NotFound
                raise Exception("Error from server (NotFound): pod not found")
            elif call_count[0] == 2:
                # Reconnect debug pod creation
                return mock_reconnect_result
            else:
                # Retry rsh command succeeds
                return mock_cmd_result

        mock_oc.invoke.side_effect = invoke_side_effect

        with patch('in_cluster_checks.core.executor.time'), \
             patch('in_cluster_checks.core.executor.atexit'):
            rc, out, err = executor.execute_cmd("echo test")

        assert rc == 0
        assert out == "output"

    @patch('in_cluster_checks.core.executor.oc')
    def test_execute_cmd_other_exception_reraises(self, mock_oc):
        """Test that non-NotFound exceptions are re-raised."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        mock_oc.invoke.side_effect = Exception("Some other error")

        with pytest.raises(Exception, match="Some other error"):
            executor.execute_cmd("echo test")

    @patch('in_cluster_checks.core.executor.oc')
    def test_get_output_from_run_cmd_success(self, mock_oc):
        """Test get_output_from_run_cmd on success."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        mock_result = Mock()
        mock_result.status.return_value = 0
        mock_result.out.return_value = "  output with spaces  \n"
        mock_result.err.return_value = ""
        mock_oc.invoke.return_value = mock_result

        output = executor.get_output_from_run_cmd("echo test")

        assert output == "output with spaces"

    @patch('in_cluster_checks.core.executor.oc')
    def test_get_output_from_run_cmd_failure(self, mock_oc):
        """Test get_output_from_run_cmd on command failure."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        mock_result = Mock()
        mock_result.status.return_value = 1
        mock_result.out.return_value = ""
        mock_result.err.return_value = "error message"
        mock_oc.invoke.return_value = mock_result

        with pytest.raises(UnExpectedSystemOutput) as exc_info:
            executor.get_output_from_run_cmd("failing command")

        assert "exit code: 1" in str(exc_info.value)
        assert exc_info.value.ip == "192.168.1.10"
        assert exc_info.value.cmd == "failing command"

    @patch('in_cluster_checks.core.executor.oc')
    def test_get_output_from_run_cmd_no_output_timeout_message(self, mock_oc):
        """Test timeout message when no output."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        mock_result = Mock()
        mock_result.status.return_value = 124  # Timeout exit code
        mock_result.out.return_value = ""
        mock_result.err.return_value = ""
        mock_oc.invoke.return_value = mock_result

        with pytest.raises(UnExpectedSystemOutput) as exc_info:
            executor.get_output_from_run_cmd("slow command")

        assert "No output from command" in exc_info.value.message
        assert "timed out" in exc_info.value.message

    @patch('in_cluster_checks.core.executor.oc')
    def test_reconnect(self, mock_oc):
        """Test reconnect method."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "old-pod"

        # Mock close and connect
        with patch.object(executor, 'close_connection') as mock_close, \
             patch.object(executor, 'connect') as mock_connect:
            executor.reconnect()

            mock_close.assert_called_once()
            mock_connect.assert_called_once()
            assert executor.is_connected is False
            assert executor._pod_id is None

    @patch('in_cluster_checks.core.executor.oc')
    def test_close_connection_success(self, mock_oc):
        """Test successful connection close."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"
        executor.is_local = False

        # Mock pod deletion
        mock_pod = Mock()
        mock_pod.name.return_value = "test-pod"
        mock_oc.get_pods_by_node.return_value = [mock_pod]

        executor.close_connection()

        assert executor.is_connected is False
        assert executor._pod_id is None
        mock_oc.delete.assert_called_once_with(mock_pod, cmd_args=['--grace-period=0', '--force'])

    @patch('in_cluster_checks.core.executor.oc')
    def test_close_connection_failure(self, mock_oc):
        """Test connection close handles deletion failure gracefully."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"
        executor.is_local = False

        mock_oc.get_pods_by_node.side_effect = Exception("Delete failed")

        # Should not raise exception
        executor.close_connection()

        assert executor.is_connected is False
        assert executor._pod_id is None

    @patch('in_cluster_checks.core.executor.oc')
    def test_close_connection_local(self, mock_oc):
        """Test close_connection skips for local executor."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_local = True
        executor._pod_id = "test-pod"

        executor.close_connection()

        # Should not try to delete pod
        mock_oc.get_pods_by_node.assert_not_called()

    @patch('in_cluster_checks.core.executor.oc')
    def test_get_host_name(self, mock_oc):
        """Test get_host_name returns node name."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        assert executor.get_host_name() == "test-node"

    @patch('in_cluster_checks.core.executor.oc')
    def test_get_host_ip(self, mock_oc):
        """Test get_host_ip returns node IP."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        assert executor.get_host_ip() == "192.168.1.10"

    @patch('in_cluster_checks.core.executor.oc')
    def test_add_role(self, mock_oc):
        """Test adding a role to an executor."""
        executor = NodeExecutor("test-node", "192.168.1.10", roles=[Objectives.MASTERS, Objectives.ALL_NODES])

        # Add ONE_MASTER role
        executor.add_role(Objectives.ONE_MASTER)

        assert Objectives.ONE_MASTER in executor.roles
        assert len(executor.roles) == 3
        assert executor.roles == [Objectives.MASTERS, Objectives.ALL_NODES, Objectives.ONE_MASTER]

    @patch('in_cluster_checks.core.executor.oc')
    def test_add_role_no_duplicates(self, mock_oc):
        """Test that adding same role twice doesn't create duplicates."""
        executor = NodeExecutor("test-node", "192.168.1.10", roles=[Objectives.MASTERS, Objectives.ALL_NODES])

        # Add ONE_MASTER role twice
        executor.add_role(Objectives.ONE_MASTER)
        executor.add_role(Objectives.ONE_MASTER)

        assert executor.roles.count(Objectives.ONE_MASTER) == 1
        assert len(executor.roles) == 3

    @patch('in_cluster_checks.core.executor.oc')
    def test_thread_lock_prevents_parallel_execution(self, mock_oc):
        """Test that thread lock prevents parallel command execution on same host."""
        executor = NodeExecutor("test-node", "192.168.1.10")
        executor.is_connected = True
        executor._pod_id = "test-pod"

        execution_order = []

        def slow_command(*args, **kwargs):
            mock_result = Mock()
            execution_order.append("start")
            time.sleep(0.1)
            execution_order.append("end")
            mock_result.status.return_value = 0
            mock_result.out.return_value = "output"
            mock_result.err.return_value = ""
            return mock_result

        mock_oc.invoke.side_effect = slow_command

        def run_command():
            executor.execute_cmd("echo test")

        thread1 = threading.Thread(target=run_command)
        thread2 = threading.Thread(target=run_command)

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        assert execution_order == ["start", "end", "start", "end"]


class TestOrchestratorExecutor:
    """Test OrchestratorExecutor functionality."""

    def test_orchestrator_executor_attributes(self):
        """Test OrchestratorExecutor has correct attributes."""
        executor = OrchestratorExecutor()

        assert executor.host_name == "in-cluster-orchestrator"
        assert executor.node_name == "in-cluster-orchestrator"
        assert executor.ip == "127.0.0.1"
        assert Objectives.ORCHESTRATOR in executor.roles
        assert executor.node_labels == ""
        assert executor.is_local is True
        assert executor.is_connected is True

    def test_orchestrator_executor_connect_noop(self):
        """Test that connect() is a no-op for orchestrator."""
        executor = OrchestratorExecutor()
        # Should not raise exception
        executor.connect()
        assert executor.is_connected is True

    def test_orchestrator_executor_execute_cmd_raises(self):
        """Test that execute_cmd raises NotImplementedError."""
        executor = OrchestratorExecutor()

        with pytest.raises(NotImplementedError) as exc_info:
            executor.execute_cmd("pwd")

        assert "run_oc_command" in str(exc_info.value)
        assert "run_rsh_cmd" in str(exc_info.value)

    def test_orchestrator_executor_close_connection_noop(self):
        """Test that close_connection() is a no-op for orchestrator."""
        executor = OrchestratorExecutor()
        # Should not raise exception
        executor.close_connection()
        assert executor.is_connected is True
