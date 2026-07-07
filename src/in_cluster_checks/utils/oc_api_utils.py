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

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import openshift_client as oc

from in_cluster_checks import global_config
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.utils.parsing_utils import parse_json
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class OcApiUtils:
    """
    Utility class for OpenShift cluster API access.

    Provides methods to query Kubernetes/OpenShift resources and execute
    commands in pods using the openshift_client library.

    This class is instantiated by OrchestratorRule and OrchestratorDataCollector
    to provide consistent cluster API access via `self.oc_api`.
    """

    # Fields to show in debug output for common resource types (equivalent to -o wide)
    DEBUG_FIELDS_MAP = {
        "pod": ["namespace", "name", "ready", "status", "restarts", "age", "ip", "node"],
        "deployment": ["namespace", "name", "ready", "up-to-date", "available", "age"],
        "statefulset": ["namespace", "name", "ready", "age"],
        "node": [
            "name",
            "status",
            "roles",
            "age",
            "version",
            "internal-ip",
            "external-ip",
            "os-image",
            "kernel-version",
            "container-runtime",
        ],
        "namespace": ["name", "status", "age"],
        "daemonset": ["namespace", "name", "desired", "current", "ready", "up-to-date", "available", "age"],
    }

    def __init__(self, operator):
        """
        Initialize with operator instance.

        Args:
            operator: OrchestratorRule or OrchestratorDataCollector instance
                     (provides _add_cmd_to_log, logger, get_host_ip methods)
        """
        self.operator = operator
        self.logger = logging.getLogger(__name__)

    def _debug_log(self, message: str, obj=None, resource_type: str = None, text: str = None):
        """
        Print debug output in standardized format when --debug-rule is active.

        Args:
            message: Debug message to print
            obj: Optional resource object or list of objects to format as JSON
            resource_type: Optional resource type (e.g., 'pod', 'deployment') for field filtering
            text: Optional pre-formatted text to print (e.g., command output)
        """
        if not global_config.debug_rule_flag:
            return

        print(f"\n[DEBUG] {message}", flush=True)

        if obj is not None:
            # Convert single object to list for uniform handling
            objects = obj if isinstance(obj, list) else [obj]

            if not objects:
                print("[DEBUG] No resources found", flush=True)
            else:
                # Extract relevant fields for each object
                formatted_objects = []
                for resource_obj in objects:
                    resource_dict = self._extract_debug_fields(resource_obj, resource_type)
                    if resource_dict:
                        formatted_objects.append(resource_dict)

                # Print as pretty JSON
                print(json.dumps(formatted_objects, indent=2), flush=True)

        if text is not None:
            print(self._truncate_output(text), flush=True)

        print("=" * 60, flush=True)

    def _truncate_output(self, text: str, max_lines: int = 100) -> str:
        """
        Truncate long text output for debug display.

        Args:
            text: Text to truncate
            max_lines: Maximum number of lines to show (default: 100)

        Returns:
            Truncated text with indicator if lines were cut
        """
        if not text:
            return ""

        lines = text.splitlines()
        if len(lines) <= max_lines:
            return text

        truncated = "\n".join(lines[:max_lines])
        truncated += f"\n... ({len(lines) - max_lines} more lines truncated)"
        return truncated

    def _extract_debug_fields(self, resource_obj, resource_type: str = None) -> dict:
        """
        Extract relevant fields from resource object for debug output.

        Shows only fields equivalent to 'oc get <resource> -o wide' output.
        Uses DEBUG_FIELDS_MAP to determine which fields to extract for each resource type.

        Args:
            resource_obj: Resource object from openshift_client
            resource_type: Resource type (e.g., 'pod', 'deployment')

        Returns:
            Dictionary with relevant fields for debug output, in the order defined by DEBUG_FIELDS_MAP
        """
        if not resource_obj:
            return {}

        # Get full resource dict
        try:
            full_dict = resource_obj.as_dict()
        except Exception:
            # Fallback if as_dict() fails
            return {"name": str(resource_obj)}

        metadata = full_dict.get("metadata", {})
        spec = full_dict.get("spec", {})
        status = full_dict.get("status", {})

        # Detect resource type from object if not provided
        if not resource_type:
            kind = full_dict.get("kind", "").lower()
            resource_type = kind if kind else "unknown"

        # Get field mapping for this resource type
        field_list = self.DEBUG_FIELDS_MAP.get(resource_type)
        if not field_list:
            # Generic resource - return name, namespace (if applicable), and age
            result = {"name": metadata.get("name", "unknown")}
            if resource_type not in ("node", "namespace"):
                result["namespace"] = metadata.get("namespace", "")
            result["age"] = self._calculate_age(metadata.get("creationTimestamp", ""))
            return result

        # Build result dict in the order defined by DEBUG_FIELDS_MAP
        result = {}
        for field in field_list:
            result[field] = self._get_field_value(field, metadata, spec, status, resource_type)

        return result

    def _get_field_value(self, field: str, metadata: dict, spec: dict, status: dict, resource_type: str) -> Any:
        """
        Get the value for a specific field from the resource object.

        Args:
            field: Field name from DEBUG_FIELDS_MAP
            metadata: Resource metadata dict
            spec: Resource spec dict
            status: Resource status dict
            resource_type: Resource type (e.g., 'pod', 'deployment')

        Returns:
            Field value (str, int, or other types depending on the field)
        """
        # Common fields across all resources
        if field == "name":
            return metadata.get("name", "unknown")
        if field == "namespace":
            return metadata.get("namespace", "")
        if field == "age":
            return self._calculate_age(metadata.get("creationTimestamp", ""))

        # Pod-specific fields
        if resource_type == "pod":
            if field == "ready":
                return self._get_pod_ready_status(status)
            if field == "status":
                return status.get("phase", "Unknown")
            if field == "restarts":
                return self._get_pod_restarts(status)
            if field == "ip":
                return status.get("podIP", "")
            if field == "node":
                return spec.get("nodeName", "")

        # Deployment-specific fields
        elif resource_type == "deployment":
            if field == "ready":
                replicas = spec.get("replicas", 0)
                ready_replicas = status.get("readyReplicas", 0)
                return f"{ready_replicas}/{replicas}"
            if field == "up-to-date":
                return status.get("updatedReplicas", 0)
            if field == "available":
                return status.get("availableReplicas", 0)

        # StatefulSet-specific fields
        elif resource_type == "statefulset":
            if field == "ready":
                replicas = spec.get("replicas", 0)
                ready_replicas = status.get("readyReplicas", 0)
                return f"{ready_replicas}/{replicas}"

        # Node-specific fields
        elif resource_type == "node":
            if field == "status":
                return self._get_node_status(status)
            if field == "roles":
                return ",".join(
                    [
                        role.replace("node-role.kubernetes.io/", "")
                        for role in metadata.get("labels", {}).keys()
                        if role.startswith("node-role.kubernetes.io/")
                    ]
                )
            if field == "version":
                return status.get("nodeInfo", {}).get("kubeletVersion", "")
            if field in ("internal-ip", "external-ip"):
                addresses = status.get("addresses", [])
                addr_type = "InternalIP" if field == "internal-ip" else "ExternalIP"
                for addr in addresses:
                    if addr.get("type") == addr_type:
                        return addr.get("address", "")
                return "<none>" if field == "external-ip" else ""
            if field == "os-image":
                return status.get("nodeInfo", {}).get("osImage", "")
            if field == "kernel-version":
                return status.get("nodeInfo", {}).get("kernelVersion", "")
            if field == "container-runtime":
                return status.get("nodeInfo", {}).get("containerRuntimeVersion", "")

        # Namespace-specific fields
        elif resource_type == "namespace":
            if field == "status":
                return status.get("phase", "Unknown")

        # DaemonSet-specific fields
        elif resource_type == "daemonset":
            if field == "desired":
                return status.get("desiredNumberScheduled", 0)
            if field == "current":
                return status.get("currentNumberScheduled", 0)
            if field == "ready":
                return status.get("numberReady", 0)
            if field == "up-to-date":
                return status.get("updatedNumberScheduled", 0)
            if field == "available":
                return status.get("numberAvailable", 0)

        # Unknown field
        return ""

    def _get_pod_ready_status(self, status: dict) -> str:
        """Get pod ready status in 'X/Y' format."""
        container_statuses = status.get("containerStatuses", [])
        if not container_statuses:
            return "0/0"
        ready_count = sum(1 for c in container_statuses if c.get("ready", False))
        total_count = len(container_statuses)
        return f"{ready_count}/{total_count}"

    def _get_pod_restarts(self, status: dict) -> int:
        """Get total pod restart count across all containers."""
        container_statuses = status.get("containerStatuses", [])
        return sum(c.get("restartCount", 0) for c in container_statuses)

    def _get_node_status(self, status: dict) -> str:
        """Get node status from conditions."""
        conditions = status.get("conditions", [])
        for condition in conditions:
            if condition.get("type") == "Ready":
                return "Ready" if condition.get("status") == "True" else "NotReady"
        return "Unknown"

    def _calculate_age(self, creation_timestamp: str) -> str:
        """
        Calculate age in human-readable format (e.g., '5d', '3h', '45m', '30s').

        Args:
            creation_timestamp: ISO 8601 timestamp string (e.g., '2024-01-15T10:30:00Z')

        Returns:
            Age string in format used by 'oc get -o wide' (e.g., '5d', '3h', '45m', '30s')
        """
        if not creation_timestamp:
            return "unknown"

        try:
            # Parse the creation timestamp
            created_dt = datetime.fromisoformat(creation_timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_seconds = int((now - created_dt).total_seconds())

            # Calculate days, hours, minutes, seconds
            days = age_seconds // 86400
            if days > 0:
                return f"{days}d"

            hours = age_seconds // 3600
            if hours > 0:
                return f"{hours}h"

            minutes = age_seconds // 60
            if minutes > 0:
                return f"{minutes}m"

            return f"{age_seconds}s"

        except (ValueError, AttributeError):
            # If parsing fails, return the original timestamp
            return creation_timestamp

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
            - If single=False: List of resource objects (empty list if none found)

        Raises:
            ValueError: If both namespace and all_namespaces are specified
            OpenShiftPythonException: If command fails (e.g., invalid resource type, timeout)
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
        self._debug_log(f"Executing command via oc.selector: {cmd_str}")

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
                    result = selector.object(ignore_not_found=True) if single else selector.objects()
            else:
                selector = oc.selector(resource_type, **selector_kwargs)
                result = selector.object(ignore_not_found=True) if single else selector.objects()

            # In debug mode, print results after execution with limited fields
            # Extract base resource type (e.g., "pod" from "pod" or "deployment" from "deployment.apps")
            base_type = resource_type.split("/")[-1].split(".")[0]

            if single:
                result_name = result.name() if result else "None"
                self._debug_log(
                    f"Command result: {result_name} (showing limited fields equivalent to -o wide)",
                    obj=result,
                    resource_type=base_type,
                )
            else:
                msg = f"Found {len(result)} {base_type}(s) (showing limited fields equivalent to -o wide)"
                self._debug_log(msg, obj=result, resource_type=base_type)

            return result

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

        self._debug_log(f"Executing command via oc.invoke: {cmd_str}")

        with oc.timeout(timeout):
            result = oc.invoke(command, args, auto_raise=False)
            rc = result.status()
            out = result.out()
            err = result.err()

            # Print command output in debug mode
            self._debug_log(f"Command returned code: rc={rc}")
            if out:
                self._debug_log("Command output:", text=out)
            if err:
                self._debug_log("Command error:", text=err)

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

    def get_operator_subscriptions(self, namespace: Optional[str] = None) -> dict:
        """Fetch operator Subscription resources from the cluster.

        Args:
            namespace: Optional namespace to query. Defaults to --all-namespaces.

        Returns:
            Parsed JSON dict of the subscriptions response.

        Raises:
            UnExpectedSystemOutput: If the command fails or JSON output cannot be parsed.
        """
        if namespace:
            args = ["subscriptions.operators.coreos.com", "-n", namespace, "-o", "json"]
            cmd_desc = f"oc get subscriptions.operators.coreos.com -n {namespace} -o json"
        else:
            args = ["subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"]
            cmd_desc = "oc get subscriptions.operators.coreos.com --all-namespaces -o json"

        _, subscriptions_output, _ = self.run_oc_command("get", args, timeout=45)

        return parse_json(subscriptions_output, cmd_desc, self.operator.get_host_ip())
