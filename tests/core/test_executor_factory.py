"""Tests for NodeExecutorFactory."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from openshift_in_cluster_checks.core.executor_factory import NodeExecutorFactory
from openshift_in_cluster_checks.utils.enums import Objectives


class TestNodeExecutorFactory:
    """Test NodeExecutorFactory."""

    def test_init_without_openshift_client(self):
        """Test initialization when openshift_client is not available."""
        # Mock oc as None in the module
        with patch("openshift_in_cluster_checks.core.executor_factory.oc", None):
            with pytest.raises(ImportError, match="openshift_client library is required"):
                NodeExecutorFactory()

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_get_roles_from_labels_master(self, mock_oc):
        """Test role extraction for master node."""
        factory = NodeExecutorFactory()

        node_dict = {
            "metadata": {
                "labels": {
                    "node-role.kubernetes.io/master": "",
                    "node-role.kubernetes.io/control-plane": "",
                }
            }
        }

        roles = factory._get_roles_from_labels(node_dict)
        assert Objectives.MASTERS in roles

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_get_roles_from_labels_worker(self, mock_oc):
        """Test role extraction for worker node."""
        factory = NodeExecutorFactory()

        node_dict = {
            "metadata": {
                "labels": {
                    "node-role.kubernetes.io/worker": "",
                }
            }
        }

        roles = factory._get_roles_from_labels(node_dict)
        assert Objectives.WORKERS in roles

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_get_roles_from_labels_multiple(self, mock_oc):
        """Test role extraction for node with multiple roles."""
        factory = NodeExecutorFactory()

        node_dict = {
            "metadata": {
                "labels": {
                    "node-role.kubernetes.io/worker": "",
                    "node-role.kubernetes.io/infra": "",
                }
            }
        }

        roles = factory._get_roles_from_labels(node_dict)
        assert Objectives.WORKERS in roles
        assert Objectives.INFRA in roles

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_get_roles_from_labels_fallback_to_all_nodes(self, mock_oc):
        """Test role extraction falls back to ALL_NODES when no known roles."""
        factory = NodeExecutorFactory()

        node_dict = {"metadata": {"labels": {}}}

        roles = factory._get_roles_from_labels(node_dict)
        assert Objectives.ALL_NODES in roles

    @patch("openshift_in_cluster_checks.core.executor_factory.NodeExecutor")
    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_build_host_executors(self, mock_oc, mock_executor_class):
        """Test building host executors from cluster nodes."""
        factory = NodeExecutorFactory()

        # Mock node objects
        mock_node1 = Mock()
        mock_node1.as_dict.return_value = {
            "metadata": {
                "name": "master-0",
                "labels": {"node-role.kubernetes.io/master": ""},
            },
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": "192.168.1.10"},
                ]
            },
        }

        mock_node2 = Mock()
        mock_node2.as_dict.return_value = {
            "metadata": {
                "name": "worker-0",
                "labels": {"node-role.kubernetes.io/worker": ""},
            },
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": "192.168.1.20"},
                ]
            },
        }

        mock_selector = Mock()
        mock_selector.objects.return_value = [mock_node1, mock_node2]
        mock_oc.selector.return_value = mock_selector

        # Mock NodeExecutor instances
        mock_executor1 = Mock()
        mock_executor2 = Mock()
        mock_executor_class.side_effect = [mock_executor1, mock_executor2]

        executors = factory.build_host_executors()

        # Verify NodeExecutor was created for each node
        assert len(executors) == 2
        assert "master-0" in executors
        assert "worker-0" in executors

        # Verify NodeExecutor was called with correct arguments
        assert mock_executor_class.call_count == 2
        # First call should be for master-0
        first_call_args = mock_executor_class.call_args_list[0]
        assert first_call_args[0][0] == "master-0"
        assert first_call_args[0][1] == "192.168.1.10"
        assert Objectives.MASTERS in first_call_args[1]["roles"]

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_connect_all(self, mock_oc):
        """Test connecting to all executors."""
        factory = NodeExecutorFactory()

        mock_executor1 = Mock()
        mock_executor2 = Mock()
        factory._host_executors_dict = {"node1": mock_executor1, "node2": mock_executor2}

        factory.connect_all()

        mock_executor1.connect.assert_called_once()
        mock_executor2.connect.assert_called_once()

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_disconnect_all(self, mock_oc):
        """Test disconnecting from all executors."""
        factory = NodeExecutorFactory()

        mock_executor1 = Mock()
        mock_executor2 = Mock()
        factory._host_executors_dict = {"node1": mock_executor1, "node2": mock_executor2}

        factory.disconnect_all()

        mock_executor1.close_connection.assert_called_once()
        mock_executor2.close_connection.assert_called_once()

    @patch("openshift_in_cluster_checks.core.executor_factory.oc")
    def test_disconnect_all_continues_on_error(self, mock_oc):
        """Test that disconnect_all continues even if one executor fails."""
        factory = NodeExecutorFactory()

        mock_executor1 = Mock()
        mock_executor1.close_connection.side_effect = Exception("Connection error")
        mock_executor2 = Mock()
        factory._host_executors_dict = {"node1": mock_executor1, "node2": mock_executor2}

        # Should not raise, should continue to disconnect executor2
        factory.disconnect_all()

        mock_executor1.close_connection.assert_called_once()
        mock_executor2.close_connection.assert_called_once()
