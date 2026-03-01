"""Tests for storage validations."""

from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.rule import PrerequisiteResult, RuleResult
from in_cluster_checks.rules.storage.storage_validations import CephOsdTreeWorks, CephRule
from in_cluster_checks.utils.enums import Objectives


# CephRule Base Class Tests


def test_ceph_rule_prerequisite_fulfilled():
    """Test CephRule prerequisite check when openshift-storage namespace and operator pod exist."""
    # Create a minimal concrete subclass for testing
    class TestCephRule(CephRule):
        objective_hosts = [Objectives.ORCHESTRATOR]
        unique_name = "test_ceph_rule"
        title = "Test Ceph Rule"

        def run_rule(self):
            return RuleResult.passed()

    with patch('openshift_client.selector') as mock_selector:
        mock_namespace = Mock()
        mock_selector.return_value.objects.return_value = [mock_namespace]

        rule = TestCephRule(node_executors={})

        # Mock _get_pod_name to return operator pod
        rule._get_pod_name = Mock(return_value="rook-ceph-operator-67890")

        result = rule.is_prerequisite_fulfilled()

        assert result.fulfilled is True
        mock_selector.assert_called_with("namespace/openshift-storage")
        rule._get_pod_name.assert_called_with("openshift-storage", {"app": "rook-ceph-operator"})


def test_ceph_rule_prerequisite_not_fulfilled():
    """Test CephRule prerequisite check when openshift-storage namespace doesn't exist."""
    # Create a minimal concrete subclass for testing
    class TestCephRule(CephRule):
        objective_hosts = [Objectives.ORCHESTRATOR]
        unique_name = "test_ceph_rule"
        title = "Test Ceph Rule"

        def run_rule(self):
            return RuleResult.passed()

    with patch('openshift_client.selector') as mock_selector:
        # Mock failed namespace check (empty list)
        mock_selector.return_value.objects.return_value = []

        rule = TestCephRule(node_executors={})
        result = rule.is_prerequisite_fulfilled()

        assert result.fulfilled is False
        assert "rook-ceph-operator pod" in result.message or "namespace not found" in result.message


def test_ceph_rule_prerequisite_no_operator_pod():
    """Test CephRule prerequisite check when namespace exists but operator pod doesn't."""
    # Create a minimal concrete subclass for testing
    class TestCephRule(CephRule):
        objective_hosts = [Objectives.ORCHESTRATOR]
        unique_name = "test_ceph_rule"
        title = "Test Ceph Rule"

        def run_rule(self):
            return RuleResult.passed()

    with patch('openshift_client.selector') as mock_selector:
        mock_namespace = Mock()
        mock_selector.return_value.objects.return_value = [mock_namespace]

        rule = TestCephRule(node_executors={})

        # Mock _get_pod_name to return None (no operator pod found)
        rule._get_pod_name = Mock(return_value=None)

        result = rule.is_prerequisite_fulfilled()

        assert result.fulfilled is False
        assert "No rook-ceph-operator pod found" in result.message
        rule._get_pod_name.assert_called_with("openshift-storage", {"app": "rook-ceph-operator"})


def test_ceph_rule_get_ceph_pod_with_tools_pod():
    """Test _get_ceph_pod when rook-ceph-tools pod is available."""
    # Create a minimal concrete subclass for testing
    class TestCephRule(CephRule):
        objective_hosts = [Objectives.ORCHESTRATOR]
        unique_name = "test_ceph_rule"
        title = "Test Ceph Rule"

        def run_rule(self):
            return RuleResult.passed()

    rule = TestCephRule(node_executors={})

    # Mock _get_pod_name to return tools pod
    rule._get_pod_name = Mock(side_effect=lambda ns, labels, log_errors=True, timeout=30: "rook-ceph-tools-12345" if labels.get("app") == "rook-ceph-tools" else None)

    namespace, pod_name, ceph_config_args = rule._get_ceph_pod()

    assert namespace == "openshift-storage"
    assert pod_name == "rook-ceph-tools-12345"
    assert ceph_config_args == ""


def test_ceph_rule_get_ceph_pod_with_operator_pod():
    """Test _get_ceph_pod when only operator pod is available."""
    # Create a minimal concrete subclass for testing
    class TestCephRule(CephRule):
        objective_hosts = [Objectives.ORCHESTRATOR]
        unique_name = "test_ceph_rule"
        title = "Test Ceph Rule"

        def run_rule(self):
            return RuleResult.passed()

    rule = TestCephRule(node_executors={})

    # Mock _get_pod_name to return operator pod only
    def mock_get_pod_name(ns, labels, log_errors=True, timeout=30):
        if labels.get("app") == "rook-ceph-tools":
            return None
        if labels.get("app") == "rook-ceph-operator":
            return "rook-ceph-operator-67890"
        return None

    rule._get_pod_name = Mock(side_effect=mock_get_pod_name)

    namespace, pod_name, ceph_config_args = rule._get_ceph_pod()

    assert namespace == "openshift-storage"
    assert pod_name == "rook-ceph-operator-67890"
    assert ceph_config_args == "-c /var/lib/rook/openshift-storage/openshift-storage.config"




# CephOsdTreeWorks Tests


def test_ceph_osd_tree_works_attributes():
    """Test CephOsdTreeWorks has correct attributes."""
    assert CephOsdTreeWorks.unique_name == "ceph_osd_tree_valid"
    assert CephOsdTreeWorks.title == "Check if ceph osd tree working"
    assert Objectives.ORCHESTRATOR in CephOsdTreeWorks.objective_hosts


def test_ceph_osd_tree_works_prerequisite_fulfilled():
    """Test prerequisite check when openshift-storage namespace and operator pod exist."""
    with patch('openshift_client.selector') as mock_selector:
        # Mock successful namespace check
        mock_namespace = Mock()
        mock_selector.return_value.objects.return_value = [mock_namespace]

        rule = CephOsdTreeWorks(node_executors={})

        # Mock _get_pod_name to return operator pod
        rule._get_pod_name = Mock(return_value="rook-ceph-operator-67890")

        result = rule.is_prerequisite_fulfilled()

        assert result.fulfilled is True
        rule._get_pod_name.assert_called_with("openshift-storage", {"app": "rook-ceph-operator"})


def test_ceph_osd_tree_works_prerequisite_not_fulfilled():
    """Test prerequisite check when openshift-storage namespace doesn't exist."""
    with patch('openshift_client.selector') as mock_selector:
        # Mock failed namespace check (empty list)
        mock_selector.return_value.objects.return_value = []

        rule = CephOsdTreeWorks(node_executors={})
        result = rule.is_prerequisite_fulfilled()

        assert result.fulfilled is False
        assert "rook-ceph-operator pod" in result.message or "namespace not found" in result.message


def test_ceph_osd_tree_works_passed(capsys):
    """Test rule passes when ceph osd tree succeeds."""
    rule = CephOsdTreeWorks(node_executors={})

    # Mock _get_ceph_pod to return pod info
    rule._get_ceph_pod = Mock(return_value=("openshift-storage", "rook-ceph-tools-12345", ""))

    # Mock run_rsh_cmd to return success
    rule.run_rsh_cmd = Mock(return_value=(0, "ID CLASS WEIGHT  TYPE NAME       STATUS REWEIGHT PRI-AFF\n-1       3.00000 root default", ""))

    result = rule.run_rule()

    assert isinstance(result, RuleResult)
    assert result.status.value == "pass"


def test_ceph_osd_tree_works_failed(capsys):
    """Test rule fails when ceph osd tree fails."""
    rule = CephOsdTreeWorks(node_executors={})

    # Mock _get_ceph_pod to return pod info
    rule._get_ceph_pod = Mock(return_value=("openshift-storage", "rook-ceph-tools-12345", ""))

    # Mock run_rsh_cmd to return failure
    rule.run_rsh_cmd = Mock(return_value=(1, "", "Error: unable to connect to ceph cluster"))

    result = rule.run_rule()

    assert isinstance(result, RuleResult)
    assert result.status.value == "fail"
    assert "ceph osd tree is not working" in result.message
