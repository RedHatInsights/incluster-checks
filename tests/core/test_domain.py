"""
Tests for RuleDomain base class.
"""

from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.core.executor import OrchestratorExecutor
from in_cluster_checks.core.rule import (
    OrchestratorRule,
    RuleResult,
    Rule,
)
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks import global_config
from profiles.profile import Profiles


@pytest.fixture(autouse=True)
def setup_profiles():
    """Set up profiles for all tests in this module."""
    # Reset light_run before test
    global_config.light_run = False

    # Create minimal profile configuration
    profile = Profiles()
    profile['general'] = {'general'}  # Minimal profile: general includes only itself

    # Set global config
    global_config.profiles_hierarchy = profile
    global_config.active_profile = "general"

    yield

    # Cleanup
    global_config.profiles_hierarchy = Profiles()
    global_config.active_profile = ""
    global_config.light_run = False


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


class MockRuleIncluded(Rule):
    """Mock rule included in light run."""

    objective_hosts = (Objectives.MASTERS,)
    unique_name = "mock_rule_included"
    include_in_light_run = True

    def run_rule(self) -> RuleResult:
        return RuleResult.passed()


class MockRuleExcluded(Rule):
    """Mock rule excluded from light run."""

    objective_hosts = (Objectives.MASTERS,)
    unique_name = "mock_rule_excluded"
    include_in_light_run = False

    def run_rule(self) -> RuleResult:
        return RuleResult.passed()


class MockDomainForLightRun(RuleDomain):
    """Mock domain for testing light run filtering."""

    def domain_name(self) -> str:
        return "mock_domain"

    def get_rule_classes(self) -> list[type[Rule]]:
        all_rules = [MockRuleIncluded, MockRuleExcluded]
        return self._filter_rules_for_light_run(all_rules)


class TestFilterRulesForLightRun:
    """Test _filter_rules_for_light_run() helper method."""

    def test_normal_mode_includes_all_rules(self):
        """Normal mode (light_run=False) should return all rules."""
        # Set normal mode
        global_config.light_run = False

        domain = MockDomainForLightRun()
        all_rules = [MockRuleIncluded, MockRuleExcluded]
        filtered = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered) == 2
        assert MockRuleIncluded in filtered
        assert MockRuleExcluded in filtered

    def test_light_mode_excludes_heavy_rules(self):
        """Light mode (light_run=True) should exclude rules with include_in_light_run=False."""
        # Set light mode
        global_config.light_run = True

        domain = MockDomainForLightRun()
        all_rules = [MockRuleIncluded, MockRuleExcluded]
        filtered = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered) == 1
        assert MockRuleIncluded in filtered
        assert MockRuleExcluded not in filtered

    def test_light_mode_with_all_included_rules(self):
        """Light mode with only included rules should return all."""
        global_config.light_run = True

        domain = MockDomainForLightRun()
        all_rules = [MockRuleIncluded]
        filtered = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered) == 1
        assert MockRuleIncluded in filtered

    def test_light_mode_with_all_excluded_rules(self):
        """Light mode with only excluded rules should return empty list."""
        global_config.light_run = True

        domain = MockDomainForLightRun()
        all_rules = [MockRuleExcluded]
        filtered = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered) == 0

    def test_rule_without_include_in_light_run_defaults_to_true(self):
        """Rules without include_in_light_run attribute should default to True."""

        class MockRuleNoAttribute(Rule):
            objective_hosts = (Objectives.MASTERS,)
            unique_name = "mock_rule_no_attr"

            def run_rule(self) -> RuleResult:
                return RuleResult.passed()

        global_config.light_run = True

        domain = MockDomainForLightRun()
        all_rules = [MockRuleNoAttribute]
        filtered = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered) == 1
        assert MockRuleNoAttribute in filtered

    def test_runner_build_component_map_filters_light_run_rules(self):
        """Test InClusterCheckRunner.build_component_map() reflects light-run filtering."""
        from in_cluster_checks.runner import InClusterCheckRunner

        # Create runner with light_run=True
        runner = InClusterCheckRunner(light_run=True)

        # Verify global config was set
        assert global_config.light_run is True

        # Build component map using mock domain
        domains = {"mock_domain": MockDomainForLightRun()}
        component_map = runner.build_component_map(domains)

        # Should include only MockRuleIncluded (include_in_light_run=True)
        assert "mock_rule_included" in component_map
        assert "mock_rule_excluded" not in component_map

        # Verify component path format
        assert component_map["mock_rule_included"] == f"{MockRuleIncluded.__module__}.MockRuleIncluded"

