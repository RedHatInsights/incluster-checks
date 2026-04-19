"""
Rule base classes for in-cluster checks.

Adapted from support/HealthChecks/HealthCheckCommon/validator.py
Simplified for OpenShift use case.
"""

import abc
import logging
from typing import Any, Dict

from in_cluster_checks import global_config
from in_cluster_checks.core.data_collector_runner import DataCollectorRunner
from in_cluster_checks.core.operations import Operator
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.oc_api_utils import OcApiUtils
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class Rule(Operator):
    """
    Base class for all in-cluster rule checks.

    Rules test specific aspects of the cluster and return status-based results.
    Each rule must implement:
    - set_document(): Define title, status, and failure message
    - run_rule(): Run the rule logic and return Status enum value

    Class variables that can be defined by subclasses:
    - unique_name: Unique identifier for this rule (optional, can set in set_document())
    - title: Human-readable title for this rule (optional)
    - objective_hosts: List of Objectives where this rule should run (required)
    - links: List of reference URLs (optional)
              Format: ["https://docs.example.com", "https://access.redhat.com/..."]
    """

    PREREQUISITES_CHECKS = []
    supported_profilers = {"general"}
    unique_name = None
    title = None
    links = None
    supported_profiles = {"general"}

    def __init__(self, host_executor, node_executors=None):
        """
        Initialize rule.

        Args:
            host_executor: NodeExecutor instance
            node_executors: Optional dict of {node_name: NodeExecutor} for multi-host data collection
        """
        super().__init__(host_executor)

        # Store node_executors for multi-host data collection
        self._node_executors = node_executors or {}

    def set_initial_values(self):
        """Initialize rule metadata fields."""
        super().set_initial_values()
        # Track data collector exceptions: {collector_class_name: {hostname: exception}}
        self.data_collector_exceptions = {}
        self.any_passed_data_collector = False

    def get_prerequisites(self):
        """Get list of prerequisite rules that should run first."""
        return self.PREREQUISITES_CHECKS

    def get_roles_for_current_deployment(self) -> list:
        """
        Get list of roles (Objectives) where this rule should run.

        Returns:
            List of Objectives from objective_hosts class variable
        """
        return self.objective_hosts

    @classmethod
    def get_unique_name_classmethod(cls) -> str:
        """
        Get unique operation name without instantiation.

        This allows getting the rule's unique name without creating an instance.
        Checks class variable first, returns None if not set (instance method should be used).

        Returns:
            Unique operation name if set as class variable, None otherwise
        """
        return cls.unique_name

    @classmethod
    def get_links(cls) -> list:
        """
        Get reference links without instantiation.

        Returns:
            List of reference URLs, or empty list if not set
        """
        return cls.links or []

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if prerequisites for running this rule are met.

        Override this method in subclasses to add custom prerequisite logic.

        Returns:
            PrerequisiteResult indicating if prerequisite is met with optional message

        Example:
            def is_prerequisite_fulfilled(self):
                return_code, _, _ = self.run_cmd("which hwclock")
                if return_code != 0:
                    return PrerequisiteResult.not_met("hwclock command is not available on this system")
                return PrerequisiteResult.met()
        """
        return PrerequisiteResult.met()

    @classmethod
    def is_enabled_for_active_profile(cls) -> bool:
        """Check if this rule is enabled for the currently active profile.

        Returns True if there's an intersection between the active profile's
        includes and this rule's supported_profiles.
        """
        active_profiles = global_config.profiles_hierarchy[global_config.active_profile]
        intersection_profiles = active_profiles.intersection(cls.supported_profiles)
        return bool(intersection_profiles)

    @abc.abstractmethod
    def run_rule(self) -> RuleResult:
        """
        Run the rule check.

        Must be implemented by subclasses.

        Returns:
            RuleResult with status and optional message

        Example:
            def run_rule(self):
                output = self.get_output_from_run_cmd("systemctl is-active NetworkManager")
                if output == "active":
                    return RuleResult.passed()
                else:
                    return RuleResult.failed(f"NetworkManager is not active: {output}")
        """
        raise NotImplementedError(f"run_rule() must be implemented in {self.__class__.__name__}")

    def run_data_collector(self, collector_class: type, use_parallel: bool = True, **kwargs) -> Dict[str, Any]:
        """
        Run a DataCollector on all hosts and return aggregated results.

        Args:
            collector_class: DataCollector subclass to instantiate
            use_parallel: Whether to run collectors in parallel (default: True)
            **kwargs: Arguments to pass to collect_data()

        Returns:
            Dictionary of {hostname: collected_data}
        """
        return DataCollectorRunner.execute_data_collector(self, collector_class, use_parallel, **kwargs)

    def get_data_collector_exceptions(self, collector_class: type) -> dict[str, Exception]:
        """
        Get exceptions from DataCollector execution.

        Args:
            collector_class: DataCollector class

        Returns:
            Dict of {hostname: exception} for failed nodes, empty dict if all succeeded
        """
        return self.data_collector_exceptions.get(collector_class.__name__, {})

    def _create_collector_instances(self, collector_class: type, hosts_dict: Dict[str, Any]) -> list:
        """Create collector instances for each host."""
        collector_instances = []
        for host_name, host_executor in hosts_dict.items():
            try:
                collector = collector_class(host_executor=host_executor)
                collector_instances.append(collector)
            except Exception as e:
                self.logger.error(f"Failed to create {collector_class.__name__} for {host_name}: {e}")
        return collector_instances


class OrchestratorRule(Rule):
    """
    Rule that coordinates data collection across nodes or runs oc commands in pods.

    Orchestrator rules:
    - Execute oc commands in pods using openshift_client library directly
    - Can collect data from multiple nodes via run_data_collector()
    - Can compare/validate data consistency across nodes
    - Use objective_hosts = [Objectives.ORCHESTRATOR]

    Example 1 - Data collection across nodes:
        class DnsConsistencyRule(OrchestratorRule):
            objective_hosts = [Objectives.ORCHESTRATOR]
            unique_name = "dns_consistency_check"

            def run_rule(self) -> bool:
                dns_data = self.run_data_collector(Bond0Dns)
                return self._compare_dns(dns_data)

    Example 2 - Running oc rsh commands in pods:
        class CephRule(OrchestratorRule):
            objective_hosts = [Objectives.ORCHESTRATOR]
            unique_name = "ceph_health_check"

            def run_rule(self) -> RuleResult:
                # Run command in a pod using run_rsh_cmd
                rc, out, err = self.oc_api.run_rsh_cmd("openshift-storage", "rook-ceph-tools-abc123", "ceph health")
                ...
    """

    def __init__(self, host_executor, node_executors=None):
        """
        Initialize orchestrator rule.

        Args:
            host_executor: OrchestratorExecutor instance
            node_executors: Dict of {node_name: NodeExecutor} for data collection
        """

        # OrchestratorRule now receives executor as first arg (matching Rule signature)
        self._host_executor = host_executor
        self._node_executors = node_executors or {}

        self.logger = logging.getLogger(__name__)

        # Initialize FlowsOperator attributes
        self.set_initial_values()
        self._enforce_have_document()

        # Verify objective_hosts is defined
        if not self.__class__.objective_hosts:
            raise ValueError(
                f"objective_hosts not defined for {self.__class__.__name__}. " "Please define as class variable."
            )

        # Initialize OcApiUtils for cluster API access
        self.oc_api = OcApiUtils(self)

    def run_cmd(self, cmd: SafeCmdString, timeout: int = 120) -> tuple:
        """
        Not available for OrchestratorRule - use run_rsh_cmd() instead.
        OrchestratorRule runs locally and doesn't have a host_executor.
        To run commands in pods, use run_rsh_cmd(namespace, pod, command).
        Args:
            cmd: Command (not used)
            timeout: Timeout (not used)
        Raises:
            NotImplementedError: Always raised with guidance to use run_rsh_cmd()
        """
        raise NotImplementedError(
            f"run_cmd('{cmd}', timeout={timeout}) is not available for OrchestratorRule ({self.__class__.__name__}). "
            f"Use run_rsh_cmd(namespace, pod, command) to run commands in pods instead."
        )

    # run_data_collector is inherited from Rule - no override needed
    # Rule's implementation handles multi-host collection when _node_executors is present
