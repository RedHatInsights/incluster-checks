"""
Tests for RuleDomain base class.
"""

from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.core.rule import (
    OrchestratorRule,
    RuleResult,
    Rule,
)
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.core.executor import OrchestratorExecutor


class MockRule(Rule):
    """Mock validator for testing."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "mock_validator"
    title = "Mock Rule"

    def run_rule(self):
        return RuleResult.passed()


class FailingMockRule(Rule):
    """Mock validator that always fails."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "failing_validator"
    title = "Failing Rule"

    def run_rule(self):
        return RuleResult.failed("This validation failed")


class OrchestratorMockRule(OrchestratorRule):
    """Mock orchestrator validator."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "orchestrator_validator"
    title = "Orchestrator Rule"

    def run_rule(self):
        return RuleResult.passed()

def test_orchestrator_rule_run_cmd_raises_error():
    """Test that OrchestratorRule.run_cmd() raises NotImplementedError."""
    rule = OrchestratorMockRule(host_executor=OrchestratorExecutor(), node_executors={})

    with pytest.raises(NotImplementedError) as exc_info:
        rule.run_cmd("echo test", timeout=30)

    error_msg = str(exc_info.value)
    assert "run_cmd('echo test', timeout=30)" in error_msg
    assert "orchestrator" in error_msg.lower()
    assert "run_rsh_cmd" in error_msg

class TestRuleDomain:
    """Test RuleDomain orchestration."""

    def test_domain_must_implement_domain_name(self):
        """Test that domain must implement domain_name()."""
        class IncompleteDomain(RuleDomain):
            def get_rule_classes(self):
                return []

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteDomain()

    def test_flow_must_implement_get_rule_classes(self):
        """Test that flow must implement get_rule_classes()."""
        class IncompleteDomain(RuleDomain):
            def domain_name(self):
                return "test"

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteDomain()

    def test_verify_with_passing_validator(self):
        """Test verify() with a passing validator."""
        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [MockRule]

        flow = TestDomain()

        # Create mock executor
        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]

        node_executors = {'test-node': mock_executor}

        result = flow.verify(node_executors)

        assert result['domain_name'] == 'test_domain'
        assert 'details' in result
        assert isinstance(result['details'], OrderedDict)

        # Check that validator ran on node
        assert 'test-node - 192.168.1.10' in result['details']
        validator_result = result['details']['test-node - 192.168.1.10']['mock_validator']

        assert validator_result['status'] == 'pass'
        assert validator_result['description_title'] == 'Mock Rule'

    def test_verify_with_failing_validator(self):
        """Test verify() with a failing validator."""
        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [FailingMockRule]

        flow = TestDomain()

        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]

        result = flow.verify({'test-node': mock_executor})

        validator_result = result['details']['test-node - 192.168.1.10']['failing_validator']

        assert validator_result['status'] == 'fail'
        assert validator_result['describe_msg'] == 'This validation failed'

    def test_verify_with_multiple_validators(self):
        """Test verify() with multiple validators."""
        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [MockRule, FailingMockRule]

        flow = TestDomain()

        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]

        result = flow.verify({'test-node': mock_executor})

        details = result['details']['test-node - 192.168.1.10']

        assert 'mock_validator' in details
        assert 'failing_validator' in details
        assert details['mock_validator']['status'] == 'pass'
        assert details['failing_validator']['status'] == 'fail'

    def test_verify_with_multiple_nodes(self):
        """Test verify() with multiple nodes."""
        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [MockRule]

        flow = TestDomain()

        mock_executor1 = Mock()
        mock_executor1.host_name = "node1"
        mock_executor1.ip = "192.168.1.10"
        mock_executor1.roles = ["ALL_NODES"]

        mock_executor2 = Mock()
        mock_executor2.host_name = "node2"
        mock_executor2.ip = "192.168.1.11"
        mock_executor2.roles = ["ALL_NODES"]

        node_executors = {
            'node1': mock_executor1,
            'node2': mock_executor2
        }

        result = flow.verify(node_executors)

        assert 'node1 - 192.168.1.10' in result['details']
        assert 'node2 - 192.168.1.11' in result['details']



    def test_verify_handles_validator_exception(self):
        """Test that verify() handles validator exceptions gracefully."""
        class ExceptionValidator(Rule):
            objective_hosts = [Objectives.ALL_NODES]
            unique_name = "exception_validator"
            title = "Exception Rule"

            def run_rule(self):
                raise RuntimeError("Test exception")

        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [ExceptionValidator]

        flow = TestDomain()

        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]

        result = flow.verify({'test-node': mock_executor})

        # Should have error result
        assert 'test-node - 192.168.1.10' in result['details']
        error_result = result['details']['test-node - 192.168.1.10']['exception_validator']

        assert error_result['status'] == 'skip'
        assert error_result['problem_type'] == 'NOT_PERFORMED'
        assert error_result['describe_msg'] == 'Unexpected error (details in the .json file)'
        assert 'exception' in error_result
        # Exception text includes error type and message
        assert 'RuntimeError' in error_result['exception']
        assert 'Test exception' in error_result['exception']

    def test_verify_with_orchestrator_validator(self):
        """Test verify() with orchestrator validator (no host_executor needed)."""
        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return [OrchestratorMockRule]

        flow = TestDomain()

        # Create mock node executors
        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]

        node_executors = {'test-node': mock_executor}

        result = flow.verify(node_executors)

        # Orchestrator results should be under "in-cluster-orchestrator - 127.0.0.1" key
        assert 'in-cluster-orchestrator - 127.0.0.1' in result['details']
        validator_result = result['details']['in-cluster-orchestrator - 127.0.0.1']['orchestrator_validator']

        assert validator_result['status'] == 'pass'
        assert validator_result['description_title'] == 'Orchestrator Rule'

    def test_create_instances_for_one_master_objective(self):
        """Test that ONE_MASTER objective creates single instance (ONE_MASTER role assigned by factory)."""
        # Create mock rule class with ONE_MASTER objective
        class TestOneMasterRule(Rule):
            objective_hosts = [Objectives.ONE_MASTER]
            unique_name = "test_one_master_rule"
            title = "Test ONE_MASTER Rule"

            def run_rule(self):
                return RuleResult.passed()

        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return []

        # Create mock executors - master-1 has ONE_MASTER role (assigned by factory)
        master1_executor = Mock()
        master1_executor.roles = [Objectives.MASTERS, Objectives.ALL_NODES, Objectives.ONE_MASTER]

        master2_executor = Mock()
        master2_executor.roles = [Objectives.MASTERS, Objectives.ALL_NODES]

        master3_executor = Mock()
        master3_executor.roles = [Objectives.MASTERS, Objectives.ALL_NODES]

        host_executors_dict = {
            "master-1": master1_executor,
            "master-2": master2_executor,
            "master-3": master3_executor,
        }

        # Create domain and instances
        domain = TestDomain()
        instances = domain._create_instances_for_rule(TestOneMasterRule, host_executors_dict)

        # Should create exactly ONE instance on executor with ONE_MASTER role
        assert len(instances) == 1
        assert instances[0].__class__ == TestOneMasterRule
        assert instances[0]._host_executor == master1_executor

    def test_create_instances_for_one_type_no_matching_nodes(self):
        """Test that ONE_* objective returns empty list when no nodes have the ONE_* role."""
        # Create mock rule class with ONE_WORKER objective
        class TestOneWorkerRule(Rule):
            objective_hosts = [Objectives.ONE_WORKER]
            unique_name = "test_one_worker_rule"
            title = "Test ONE_WORKER Rule"

            def run_rule(self):
                return RuleResult.passed()

        class TestDomain(RuleDomain):
            def domain_name(self):
                return "test_domain"

            def get_rule_classes(self):
                return []

        # Create mock executors - only masters (no ONE_WORKER role assigned)
        master_executor = Mock()
        master_executor.roles = [Objectives.MASTERS, Objectives.ALL_NODES, Objectives.ONE_MASTER]

        host_executors_dict = {
            "master-1": master_executor,
        }

        # Create domain and instances
        domain = TestDomain()
        instances = domain._create_instances_for_rule(TestOneWorkerRule, host_executors_dict)

        # Should return empty list (no executor with ONE_WORKER role)
        assert len(instances) == 0

