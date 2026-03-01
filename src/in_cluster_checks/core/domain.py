"""
Validation domain base classes.

Domains orchestrate multiple validators and return aggregated results.
Named "domain" to avoid confusion with OpenShift flows (scan, full-run, etc.).

Adapted from support/HealthChecks/HealthCheckCommon/flow.py
Simplified for OpenShift use case.
"""

import abc
import logging
from typing import Any, Dict, List

from in_cluster_checks import global_config
from in_cluster_checks.core.parallel_runner import ParallelRunner
from in_cluster_checks.core.printer import StructedPrinter
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.utils.enums import Objectives


class RuleDomain(abc.ABC):
    """
    Base class for rule domains.

    A domain orchestrates multiple validators, runs them, and aggregates results.
    Named "domain" instead of "flow" to avoid confusion with OpenShift flows.
    """

    def __init__(self):
        """Initialize domain."""
        self.logger = logging.getLogger(__name__)

    @abc.abstractmethod
    def domain_name(self) -> str:
        """
        Get unique name for this domain.

        Returns:
            Domain name (e.g., "network", "k8s", "etcd")
        """
        raise NotImplementedError(f"domain_name() must be implemented in {self.__class__.__name__}")

    @abc.abstractmethod
    def get_rule_classes(self) -> List[type]:
        """
        Get list of rule classes to run in this domain.

        Returns:
            List of Rule subclasses

        Example:
            return [
                OvsInterfaceAndPortFound,
                Bond0DnsServersComparison,
                LogicalSwitchNodeValidator,
            ]
        """
        raise NotImplementedError(f"get_rule_classes() must be implemented in {self.__class__.__name__}")

    def verify(self, host_executors_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run all rules in this domain using HC's parallel execution pattern.

        Args:
            host_executors_dict: Dictionary of {node_name: NodeExecutor/ContainerExecutor}

        Returns:
            Dictionary with domain results:
            {
                'domain_name': str,
                'details': OrderedDict of {host_key: {rule_name: result}}
            }
        """
        self.logger.info(f"Running domain: {self.domain_name()}")

        rule_classes = self.get_rule_classes()
        self.logger.debug(f"Domain has {len(rule_classes)} rule classes")

        printer = StructedPrinter()
        rule_groups = self._create_rule_groups(rule_classes, host_executors_dict)

        ParallelRunner.run_domain_rules_on_all_hosts(rule_groups, printer)

        details = printer.get_msg()
        printer.print_summary(self.domain_name())

        return {"domain_name": self.domain_name(), "details": details}

    def _create_rule_groups(self, rule_classes: List[type], host_executors_dict: Dict[str, Any]) -> List[List[Rule]]:
        """
        Create grouped rule instances following HC's pattern.

        HC pattern: For each rule class, create one instance per applicable host.
        Result structure: [[Rule1_node1, Rule1_node2], [Rule2_node1, Rule2_node2]]

        Args:
            rule_classes: List of Rule classes to instantiate
            host_executors_dict: Dictionary of {node_name: NodeExecutor}

        Returns:
            List of lists of rule instances, grouped by rule class
        """
        rule_groups = []

        for rule_class in rule_classes:
            if not self._matches_debug_filter(rule_class):
                continue

            instances = self._create_instances_for_rule(rule_class, host_executors_dict)

            if instances:
                rule_groups.append(instances)
                self.logger.debug(f"{rule_class.__name__}: created {len(instances)} instance(s)")

        return rule_groups

    def _create_instances_for_rule(self, rule_class: type, host_executors_dict: Dict[str, Any]) -> List[Rule]:
        """
        Create rule instances for a single rule class.

        Args:
            rule_class: Rule class to instantiate
            host_executors_dict: Dictionary of {node_name: NodeExecutor}

        Returns:
            List of rule instances
        """
        is_orchestrator = Objectives.ORCHESTRATOR in rule_class.objective_hosts
        assert not (
            is_orchestrator and len(rule_class.objective_hosts) > 1
        ), f"{rule_class.__name__}: ORCHESTRATOR must be the only objective_hosts value"

        if is_orchestrator:
            return self._create_orchestrator_instance(rule_class, host_executors_dict)
        else:
            return self._create_per_node_instances(rule_class, host_executors_dict)

    def _create_orchestrator_instance(self, rule_class: type, host_executors_dict: Dict[str, Any]) -> List[Rule]:
        """
        Create single orchestrator instance.

        Args:
            rule_class: Orchestrator rule class
            host_executors_dict: Dictionary of all node executors

        Returns:
            List with single orchestrator instance, or empty list if creation failed
        """
        try:
            rule = rule_class(node_executors=host_executors_dict)
            self.logger.debug(f"Created {rule_class.__name__} as ORCHESTRATOR")
            return [rule]
        except Exception as e:
            self.logger.error(f"Failed to instantiate {rule_class.__name__} as orchestrator: {e}")
            return []

    def _create_per_node_instances(self, rule_class: type, host_executors_dict: Dict[str, Any]) -> List[Rule]:
        """
        Create rule instances for each matching node.

        Args:
            rule_class: Rule class
            host_executors_dict: Dictionary of {node_name: NodeExecutor}

        Returns:
            List of rule instances (one per matching node)
        """
        instances = []

        for node_name, executor in host_executors_dict.items():
            if self._should_create_for_executor(rule_class, executor):
                try:
                    rule = rule_class(executor, node_executors=host_executors_dict)
                    instances.append(rule)
                    self.logger.debug(f"Created {rule_class.__name__} for {node_name}")
                except Exception as e:
                    self.logger.error(f"Failed to instantiate {rule_class.__name__} on {node_name}: {e}")

        return instances

    def _should_create_for_executor(self, rule_class: type, executor: Any) -> bool:
        """
        Check if rule should be created for the given executor.

        Args:
            rule_class: Rule class
            executor: NodeExecutor or ContainerExecutor

        Returns:
            True if rule should be created, False otherwise
        """
        executor_roles = getattr(executor, "roles", [])
        required_roles = rule_class.objective_hosts

        if executor_roles:
            has_matching_role = any(role in executor_roles for role in required_roles)
            if not has_matching_role:
                return False

        return True

    def _matches_debug_filter(self, rule_class: type) -> bool:
        """
        Check if rule matches debug filter (by unique_name or title).

        Args:
            rule_class: Rule class to check

        Returns:
            True if rule matches debug filter (or no filter set), False otherwise
        """
        if not global_config.config.debug_rule_name:
            return True

        if rule_class.unique_name == global_config.config.debug_rule_name:
            return True
        if rule_class.title == global_config.config.debug_rule_name:
            return True

        self.logger.debug(
            f"Skipping {rule_class.unique_name or rule_class.__name__} "
            f"(debug mode: only running {global_config.config.debug_rule_name})"
        )
        return False
