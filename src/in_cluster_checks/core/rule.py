"""
Rule base classes for in-cluster checks.

Adapted from support/HealthChecks/HealthCheckCommon/validator.py
Simplified for OpenShift use case.
"""

import abc
import logging
from typing import Any, Dict

import openshift_client as oc

from in_cluster_checks import global_config
from in_cluster_checks.core.data_collector_runner import DataCollectorRunner
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import FlowsOperator
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult


class Rule(FlowsOperator):
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
    """

    PREREQUISITES_CHECKS = []
    unique_name = None
    title = None

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
                rc, out, err = self.run_rsh_cmd("openshift-storage", "rook-ceph-tools-abc123", "ceph health")
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

    def run_cmd(self, cmd: str, timeout: int = 120) -> tuple:
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

    def _select_resources(
        self,
        resource_type: str,
        namespace: str | None = None,
        labels: Dict[str, str] | None = None,
        all_namespaces: bool = False,
        timeout: int = 30,
        single: bool = False,
    ) -> list | Any | None:
        """Execute oc.selector with consistent error handling and timeout management.

        This is a generic wrapper around oc.selector() that provides:
        - Consistent timeout management
        - Standardized error handling with contextual logging
        - Support for both .objects() (list) and .object() (single) patterns
        - Validation of mutually exclusive parameters

        Args:
            resource_type: Resource type to select (e.g., "node", "pod", "network.operator/cluster")
            namespace: Specific namespace to search in (mutually exclusive with all_namespaces)
            labels: Dictionary of label selectors (e.g., {"app": "myapp"})
            all_namespaces: Search across all namespaces (mutually exclusive with namespace)
            timeout: Timeout in seconds (default: 30)
            single: If True, return single object via .object() instead of list via .objects()

        Returns:
            - If single=True: Single resource object or None if not found
            - If single=False: List of resource objects (empty list if none found or error)

        Raises:
            ValueError: If both namespace and all_namespaces are specified
        """
        # Validate mutually exclusive parameters
        if namespace and all_namespaces:
            raise ValueError("Cannot specify both 'namespace' and 'all_namespaces' parameters")

        # Build command string for logging
        cmd_parts = ["oc", "get", resource_type]
        if namespace:
            cmd_parts.extend(["-n", namespace])
        elif all_namespaces:
            cmd_parts.append("-A")
        if labels:
            label_str = ",".join([f"{k}={v}" for k, v in labels.items()])
            cmd_parts.extend(["-l", label_str])
        cmd_str = " ".join(cmd_parts)
        self._add_cmd_to_log(cmd_str)

        # In debug mode, print command BEFORE execution
        if global_config.debug_rule_flag:
            print(f"\n[DEBUG] Executing: {cmd_str}", flush=True)

        try:
            with oc.timeout(timeout):
                # Build selector kwargs
                selector_kwargs = {}
                if labels:
                    selector_kwargs["labels"] = labels
                if all_namespaces:
                    selector_kwargs["all_namespaces"] = True

                # Create selector with appropriate context
                if namespace:
                    with oc.project(namespace):
                        selector = oc.selector(resource_type, **selector_kwargs)
                        result = selector.object() if single else selector.objects()
                else:
                    selector = oc.selector(resource_type, **selector_kwargs)
                    result = selector.object() if single else selector.objects()

                # In debug mode, print results after execution
                if global_config.debug_rule_flag:
                    if single:
                        print(f"[DEBUG] Result: {result.name() if result else 'None'}", flush=True)
                    else:
                        print(f"[DEBUG] Found {len(result)} resources", flush=True)
                        if result:
                            for obj in result:
                                print(f"[DEBUG]   - {obj.name()}", flush=True)
                    print("=" * 60, flush=True)

                return result

        except Exception as e:
            # In debug mode, print exception with command context
            if global_config.debug_rule_flag:
                print(f"[DEBUG] Command '{cmd_str}' failed with exception: {e}", flush=True)
                print("=" * 60, flush=True)

            # Log error with command context
            self.logger.error(f"Failed to execute command '{cmd_str}': {e}")

            # Return appropriate empty value
            return None if single else []

    def _get_pods(self, namespace: str = None, labels: dict = None, timeout: int = 30) -> list:
        """Get pods from namespace with optional label filtering.

        Args:
            namespace: Namespace to search in. If None, searches all namespaces.
            labels: Optional dict of label selectors (e.g., {"app": "rook-ceph-tools"})
            timeout: Timeout in seconds (default: 30)

        Returns:
            List of pod objects, or empty list if none found
        """
        if namespace:
            return self._select_resources("pod", namespace=namespace, labels=labels, timeout=timeout)
        else:
            return self._select_resources("pod", labels=labels, all_namespaces=True, timeout=timeout)

    def _get_pod_name(self, namespace: str, labels: dict, log_errors: bool = True, timeout: int = 30) -> str | None:
        """Get pod name from a namespace using label selectors.

        Args:
            namespace: Namespace to search in
            labels: Dictionary of label selectors (e.g., {"app": "rook-ceph-tools"})
            log_errors: Whether to log messages as errors (True) or info (False). Default: True
            timeout: Timeout in seconds (default: 30)

        Returns:
            Pod name if found, None otherwise
        """
        pods = self._get_pods(namespace=namespace, labels=labels, timeout=timeout)
        if pods:
            return pods[0].name()

        # No pods found
        error_msg = f"No pod found in {namespace} namespace with labels {labels}"
        if log_errors:
            self.logger.error(error_msg)
        else:
            self.logger.info(error_msg)
        return None

    def run_rsh_cmd(self, namespace: str, pod: str, command: str, timeout: int = 120) -> tuple:
        """
        Run command in a pod using oc rsh.

        Args:
            namespace: Namespace where the pod is located
            pod: Pod name
            command: Command to execute in the pod
            timeout: Timeout in seconds (default: 120)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        self._add_cmd_to_log(f'oc -n {namespace} rsh {pod} bash -c "{command}"')
        try:
            with oc.timeout(timeout):
                with oc.project(namespace):
                    result = oc.invoke(
                        "rsh",
                        cmd_args=[pod, "bash", "-c", command],
                        auto_raise=False,
                    )
            return result.status(), result.out(), result.err()

        except Exception as e:
            # Return error without raising exception
            error_msg = f"Failed to rsh into pod {namespace}/{pod}: {str(e)}"
            self.logger.error(error_msg)
            return 1, "", error_msg

    def run_oc_command(self, command: str, args: list, timeout: int = 120, raise_on_error: bool = True) -> tuple:
        """
        Run oc command using openshift_client library.

        Args:
            command: oc command (e.g., "get", "adm")
            args: List of command arguments (e.g., ["pods", "--all-namespaces"])
            timeout: Timeout in seconds (default: 120)
            raise_on_error: If True, raise UnExpectedSystemOutput on non-zero exit code (default: True)

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            UnExpectedSystemOutput: If command fails and raise_on_error is True
        """
        cmd_str = f"oc {command} {' '.join(args)}"
        self._add_cmd_to_log(cmd_str)

        with oc.timeout(timeout):
            result = oc.invoke(command, args, auto_raise=False)
            rc = result.status()
            out = result.out()
            err = result.err()

            if rc != 0 and raise_on_error:
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(), cmd=cmd_str, output=out + err, message=f"Command exited with code {rc}"
                )

            return rc, out, err

    def get_all_pods(self, all_namespaces: bool = True, namespace: str = None, timeout: int = 45) -> list:
        """
        Get all pods using oc get pods.

        Args:
            all_namespaces: Get pods from all namespaces (default: True)
            namespace: Specific namespace to query (overrides all_namespaces if provided)
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of pod objects (from openshift_client)
        """
        if namespace:
            cmd_str = f"oc get pods -n {namespace}"
            self._add_cmd_to_log(cmd_str)
            try:
                with oc.timeout(timeout):
                    with oc.project(namespace):
                        pod_objects = oc.selector("pods").objects()
                        return pod_objects
            except Exception as e:
                self.logger.error(f"Failed to get pods in namespace {namespace}: {e}")
                return []
        else:
            cmd_str = "oc get pods" + (" --all-namespaces" if all_namespaces else "")
            self._add_cmd_to_log(cmd_str)
            try:
                with oc.timeout(timeout):
                    pod_objects = oc.selector("pods", all_namespaces=all_namespaces).objects()
                    return pod_objects
            except Exception as e:
                self.logger.error(f"Failed to get pods: {e}")
                return []

    def get_all_nodes(self, timeout: int = 45) -> list:
        """
        Get all nodes using oc get nodes.

        Args:
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of node objects (from openshift_client)
        """
        self._add_cmd_to_log("oc get nodes")

        try:
            with oc.timeout(timeout):
                node_objects = oc.selector("nodes").objects()
                return node_objects
        except Exception as e:
            self.logger.error(f"Failed to get nodes: {e}")
            return []

    def get_all_namespaces(self, timeout: int = 45) -> list:
        """
        Get all namespaces using oc get namespaces.

        Args:
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of namespace objects (from openshift_client)
        """
        self._add_cmd_to_log("oc get namespaces")

        try:
            with oc.timeout(timeout):
                namespace_objects = oc.selector("namespaces").objects()
                return namespace_objects
        except Exception as e:
            self.logger.error(f"Failed to get namespaces: {e}")
            return []
