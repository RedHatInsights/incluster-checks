"""
OpenShift Client API utilities for orchestrator-level operations.

Provides K8s/OpenShift cluster API access using openshift_client library.
Follows FileUtils pattern - composition over inheritance.

This utility is used by:
- OrchestratorRule: Rules that coordinate across cluster
- OrchestratorDataCollector: Data collectors that query cluster resources

Usage:
    class MyRule(OrchestratorRule):
        def run_rule(self):
            pods = self.oc_api.select_resources("pod", namespace="default")
            ...

    class MyCollector(OrchestratorDataCollector):
        def collect_data(self):
            network_obj = self.oc_api.select_resources("network.operator/cluster", single=True)
            ...
"""

import logging
from typing import Any, Dict

import openshift_client as oc

from in_cluster_checks import global_config
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class OcApiUtils:
    """
    Utility class for OpenShift cluster API access.

    Provides methods to query Kubernetes/OpenShift resources and execute
    commands in pods using the openshift_client library.

    This class is instantiated by OrchestratorRule and OrchestratorDataCollector
    to provide consistent cluster API access via `self.oc_api`.
    """

    def __init__(self, operator):
        """
        Initialize with operator instance.

        Args:
            operator: OrchestratorRule or OrchestratorDataCollector instance
                     (provides _add_cmd_to_log, logger, get_host_ip methods)
        """
        self.operator = operator
        self.logger = logging.getLogger(__name__)

    def select_resources(
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
        self.operator._add_cmd_to_log(cmd_str)

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

    def get_pods(self, namespace: str = None, labels: dict = None, timeout: int = 30) -> list:
        """Get pods from namespace with optional label filtering.

        Args:
            namespace: Namespace to search in. If None, searches all namespaces.
            labels: Optional dict of label selectors (e.g., {"app": "rook-ceph-tools"})
            timeout: Timeout in seconds (default: 30)

        Returns:
            List of pod objects, or empty list if none found
        """
        if namespace:
            return self.select_resources("pod", namespace=namespace, labels=labels, timeout=timeout)
        else:
            return self.select_resources("pod", labels=labels, all_namespaces=True, timeout=timeout)

    def get_pod_name(self, namespace: str, labels: dict, log_errors: bool = True, timeout: int = 30) -> str | None:
        """Get pod name from a namespace using label selectors.

        Args:
            namespace: Namespace to search in
            labels: Dictionary of label selectors (e.g., {"app": "rook-ceph-tools"})
            log_errors: Whether to log messages as errors (True) or info (False). Default: True
            timeout: Timeout in seconds (default: 30)

        Returns:
            Pod name if found, None otherwise
        """
        pods = self.get_pods(namespace=namespace, labels=labels, timeout=timeout)
        if pods:
            return pods[0].name()

        # No pods found
        error_msg = f"No pod found in {namespace} namespace with labels {labels}"
        if log_errors:
            self.logger.error(error_msg)
        else:
            self.logger.info(error_msg)
        return None

    def run_rsh_cmd(self, namespace: str, pod: str, command: SafeCmdString, timeout: int = 120) -> tuple:
        """
        Run command in a pod using oc rsh.

        Args:
            namespace: Namespace where the pod is located
            pod: Pod name
            command: SafeCmdString object with command to execute in the pod
            timeout: Timeout in seconds (default: 120)

        Returns:
            Tuple of (return_code, stdout, stderr)

        Raises:
            TypeError: If command is not a SafeCmdString instance
        """
        # Enforce SafeCmdString usage to prevent shell injection
        if not isinstance(command, SafeCmdString):
            raise TypeError(
                f"run_rsh_cmd() requires SafeCmdString, got {type(command).__name__}. "
                f"Use: SafeCmdString('cmd {{var}}').format(var=value)"
            )

        # Convert SafeCmdString to string
        cmd_str = str(command)

        self.operator._add_cmd_to_log(f'oc -n {namespace} rsh {pod} bash -c "{cmd_str}"')
        try:
            with oc.timeout(timeout):
                with oc.project(namespace):
                    result = oc.invoke(
                        "rsh",
                        cmd_args=[pod, "bash", "-c", cmd_str],
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
        self.operator._add_cmd_to_log(cmd_str)

        with oc.timeout(timeout):
            result = oc.invoke(command, args, auto_raise=False)
            rc = result.status()
            out = result.out()
            err = result.err()

            if rc != 0 and raise_on_error:
                raise UnExpectedSystemOutput(
                    ip=self.operator.get_host_ip(),
                    cmd=cmd_str,
                    output=out + err,
                    message=f"Command exited with code {rc}",
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
            return self.select_resources("pod", namespace=namespace, timeout=timeout)
        else:
            return self.select_resources("pod", all_namespaces=all_namespaces, timeout=timeout)

    def get_all_nodes(self, timeout: int = 45) -> list:
        """
        Get all nodes using oc get nodes.

        Args:
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of node objects (from openshift_client)
        """
        return self.select_resources("node", timeout=timeout)

    def get_all_namespaces(self, timeout: int = 45) -> list:
        """
        Get all namespaces using oc get namespaces.

        Args:
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of namespace objects (from openshift_client)
        """
        return self.select_resources("namespace", timeout=timeout)

    def get_all_deployments(self, namespace: str = None, timeout: int = 45) -> list:
        """
        Get all deployments using oc get deployments.

        Args:
            namespace: Specific namespace to query. If None, gets deployments from all namespaces.
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of deployment objects (from openshift_client)
        """
        if namespace:
            return self.select_resources("deployment", namespace=namespace, timeout=timeout)
        else:
            return self.select_resources("deployment", all_namespaces=True, timeout=timeout)

    def get_all_statefulsets(self, namespace: str = None, timeout: int = 45) -> list:
        """
        Get all statefulsets using oc get statefulsets.

        Args:
            namespace: Specific namespace to query. If None, gets statefulsets from all namespaces.
            timeout: Timeout in seconds (default: 45)

        Returns:
            List of statefulset objects (from openshift_client)
        """
        if namespace:
            return self.select_resources("statefulset", namespace=namespace, timeout=timeout)
        else:
            return self.select_resources("statefulset", all_namespaces=True, timeout=timeout)

    def get_pod_status(self, pod):
        """
        Get pod status information for validation.

        Args:
            pod: Pod object from openshift_client

        Returns:
            Dictionary with pod status information, or None if pod should be skipped (e.g., completed jobs).
            Dictionary contains:
                - name: Pod name
                - phase: Pod phase (Running, Pending, Failed, etc.)
                - all_containers_ready: True if all containers are ready
                - status_message: Human-readable status message
        """
        pod_data = pod.as_dict()
        pod_name = pod_data["metadata"]["name"]
        status_dict = pod_data.get("status", {})
        phase = status_dict.get("phase", "Unknown")

        # Skip completed jobs as their phase is "Succeeded" and they are not expected to be running
        if phase == "Succeeded":
            return None

        # Check if all containers are ready
        container_statuses = status_dict.get("containerStatuses", [])
        all_ready = all(c.get("ready", False) for c in container_statuses)

        # Build status message
        if phase != "Running":
            status_message = f"{pod_name} - Phase: {phase}"
        elif not all_ready:
            status_message = f"{pod_name} - {phase}, Not all containers ready"
        else:
            status_message = f"{pod_name} - Ready"

        return {
            "name": pod_name,
            "phase": phase,
            "all_containers_ready": phase == "Running" and all_ready,
            "status_message": status_message,
        }
