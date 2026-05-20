"""Tests for OcApiUtils - select_resources error handling."""

from unittest.mock import Mock, patch

import pytest
from openshift_client import OpenShiftPythonException

from in_cluster_checks import global_config
from in_cluster_checks.utils.oc_api_utils import OcApiUtils


@pytest.fixture
def mock_operator():
    operator = Mock()
    operator._add_cmd_to_log = Mock()
    operator.get_host_ip.return_value = "10.0.0.1"
    return operator


@pytest.fixture
def oc_api(mock_operator):
    return OcApiUtils(mock_operator)


@pytest.fixture(autouse=True)
def disable_debug():
    original = global_config.debug_rule_flag
    global_config.debug_rule_flag = False
    yield
    global_config.debug_rule_flag = original


class TestSelectResources:
    """Test select_resources behavior."""

    @patch("in_cluster_checks.utils.oc_api_utils.oc")
    def test_openshift_exception_propagates(self, mock_oc, oc_api):
        mock_oc.timeout.return_value.__enter__ = Mock()
        mock_oc.timeout.return_value.__exit__ = Mock(return_value=False)
        mock_oc.selector.side_effect = OpenShiftPythonException("Unable to read object")

        with pytest.raises(OpenShiftPythonException, match="Unable to read object"):
            oc_api.select_resources("faketype")

    @patch("in_cluster_checks.utils.oc_api_utils.oc")
    def test_success_returns_objects(self, mock_oc, oc_api):
        mock_obj1 = Mock()
        mock_obj2 = Mock()
        mock_selector = Mock()
        mock_selector.objects.return_value = [mock_obj1, mock_obj2]

        mock_oc.timeout.return_value.__enter__ = Mock()
        mock_oc.timeout.return_value.__exit__ = Mock(return_value=False)
        mock_oc.selector.return_value = mock_selector

        result = oc_api.select_resources("pod")

        assert result == [mock_obj1, mock_obj2]

    @patch("in_cluster_checks.utils.oc_api_utils.oc")
    def test_single_returns_object(self, mock_oc, oc_api):
        mock_obj = Mock()
        mock_selector = Mock()
        mock_selector.object.return_value = mock_obj

        mock_oc.timeout.return_value.__enter__ = Mock()
        mock_oc.timeout.return_value.__exit__ = Mock(return_value=False)
        mock_oc.selector.return_value = mock_selector

        result = oc_api.select_resources("network.operator/cluster", single=True)

        assert result == mock_obj
        mock_selector.object.assert_called_once_with(ignore_not_found=True)

    @patch("in_cluster_checks.utils.oc_api_utils.oc")
    def test_single_not_found_returns_none(self, mock_oc, oc_api):
        mock_selector = Mock()
        mock_selector.object.return_value = None

        mock_oc.timeout.return_value.__enter__ = Mock()
        mock_oc.timeout.return_value.__exit__ = Mock(return_value=False)
        mock_oc.selector.return_value = mock_selector

        result = oc_api.select_resources("namespace/nonexistent", single=True)

        assert result is None
        mock_selector.object.assert_called_once_with(ignore_not_found=True)

    def test_validates_mutually_exclusive_params(self, oc_api):
        with pytest.raises(ValueError, match="Cannot specify both"):
            oc_api.select_resources("pod", namespace="default", all_namespaces=True)
