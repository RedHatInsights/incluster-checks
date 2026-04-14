"""
Node executor factory for creating and managing node executors.

Adapted from support's OpenshiftHostExecutorFactory.
Provides centralized creation and management of NodeExecutor instances.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

try:
    import openshift_client as oc
except ImportError:
    oc = None

from in_cluster_checks import global_config
from in_cluster_checks.core.executor import NodeExecutor
from in_cluster_checks.utils.enums import Objectives


class NodeExecutorFactory:
    """
    Factory for creating and managing NodeExecutor instances.

    Similar to HC's OpenshiftHostExecutorFactory, this class:
    - Discovers cluster nodes using openshift_client library
    - Assigns roles (MASTERS, WORKERS, etc.) based on node labels
    - Creates NodeExecutor for each node
    - Stores executors in a dictionary for access by validators
    """

    # Mapping from node role labels (node-role.kubernetes.io/*) to Objectives
    ROLE_LABEL_MAPPING = {
        "master": Objectives.MASTERS,
        "control-plane": Objectives.MASTERS,  # OCP 4.x uses control-plane instead of master
        "worker": Objectives.WORKERS,
        "app-worker": Objectives.APP_WORKERS,  # NCP-specific app worker nodes
        "infra": Objectives.INFRA,  # Infrastructure nodes
        "monitor": Objectives.MONITORS,  # Monitoring nodes (e.g., Prometheus)
    }

    # Mapping for adding ONE_* roles to selected executors (like HealthCheck's SINGLE_ROLES_TO_ADD)
    SINGLE_ROLES_TO_ADD = {
        Objectives.MASTERS: Objectives.ONE_MASTER,
        Objectives.WORKERS: Objectives.ONE_WORKER,
    }

    def __init__(self):
        """Initialize the factory."""
        if oc is None:
            raise ImportError("openshift_client library is required for NodeExecutorFactory")

        self.logger = logging.getLogger(__name__)
        self._host_executors_dict: Dict[str, NodeExecutor] = {}

    def build_host_executors(self) -> Dict[str, NodeExecutor]:
        """
        Build all host executors by querying cluster nodes.

        Uses openshift_client library like HC's OpenshiftHostExecutorFactory.

        Returns:
            Dictionary of {node_name: NodeExecutor}
        """
        self.logger.debug("Building host executors from cluster nodes using oc.selector")

        # Get all nodes using openshift_client library (same as HC)
        with oc.timeout(60 * 30):
            nodes_list = oc.selector("node").objects()

        # Build executor for each node
        for node in nodes_list:
            node_dict = node.as_dict()
            roles = self._get_roles_from_labels(node_dict)
            node_labels = self._get_role_labels_string(node_dict)
            node_name = node_dict["metadata"]["name"]
            node_ip = self._get_internal_ip(node_dict)

            if node_ip:
                self._add_host_executor(node_name, node_ip, roles, node_labels)
            else:
                self.logger.warning(f"No internal IP found for node {node_name}")

        self.logger.info(f"Built {len(self._host_executors_dict)} node executor(s)")

        # Add ONE_* roles to selected executors (like HealthCheck)
        self._add_single_roles()

        return self._host_executors_dict

    def _get_internal_ip(self, node_dict: dict) -> str:
        """
        Extract internal IP from node data.

        Args:
            node_dict: Node data from openshift_client

        Returns:
            Internal IP address or None
        """
        for address in node_dict.get("status", {}).get("addresses", []):
            if address["type"] == "InternalIP":
                return address["address"]
        return None

    def _get_roles_from_labels(self, node_dict: dict) -> List[str]:
        """
        Get list of roles for a node based on node labels.

        Exactly follows HC's pattern from OpenshiftHostExecutorFactory._get_roles_list()

        Args:
            node_dict: Node data from openshift_client

        Returns:
            List of Objectives (roles) for this node
        """
        roles = []
        node_labels = node_dict.get("metadata", {}).get("labels", {})

        # Extract role labels from node-role.kubernetes.io/* labels
        # Same pattern as HC
        role_labels = [
            key.split("node-role.kubernetes.io/")[1] for key in node_labels.keys() if "node-role.kubernetes.io/" in key
        ]

        # Map role labels to Objectives
        for role_label in role_labels:
            if role_label in self.ROLE_LABEL_MAPPING:
                objective = self.ROLE_LABEL_MAPPING[role_label]
                roles.append(objective)
                self.logger.debug(f"Mapped label '{role_label}' to objective '{objective}'")

        # All nodes get ALL_NODES role (same as HC)
        roles.append(Objectives.ALL_NODES)

        return roles

    def _get_role_labels_string(self, node_dict: dict) -> str:
        """
        Get comma-separated string of role labels for a node.

        Args:
            node_dict: Node data from openshift_client

        Returns:
            Comma-separated role labels (e.g., "control-plane,worker" or "worker")
        """
        node_labels = node_dict.get("metadata", {}).get("labels", {})

        # Extract role labels from node-role.kubernetes.io/* labels
        role_labels = [
            key.split("node-role.kubernetes.io/")[1] for key in node_labels.keys() if "node-role.kubernetes.io/" in key
        ]

        return ",".join(sorted(role_labels)) if role_labels else ""

    def _add_host_executor(self, node_name: str, node_ip: str, roles: List[str], node_labels: str = ""):
        """
        Create and store a NodeExecutor.

        Args:
            node_name: Name of the node
            node_ip: IP address of the node
            roles: List of Objectives (roles) for this node
            node_labels: Comma-separated string of node role labels (e.g., "control-plane,worker")
        """
        executor = NodeExecutor(
            node_name, node_ip, roles=roles, node_labels=node_labels, namespace=global_config.namespace
        )
        self._host_executors_dict[node_name] = executor
        self.logger.debug(
            f"Added executor for {node_name} ({node_ip}) with roles: {roles}, "
            f"labels: {node_labels}, namespace: {global_config.namespace}"
        )

    def _add_single_roles(self):
        """
        Add ONE_* roles to selected executors.

        For each multi-type role (MASTERS, WORKERS), selects one executor
        and adds the corresponding ONE_* role to it.

        Follows HealthCheck's add_single_role_from_objective() pattern from
        BaseHostExecutorsFactory.
        """
        for multi_role, single_role in self.SINGLE_ROLES_TO_ADD.items():
            # Find executors with the multi-type role
            candidates = [
                (name, executor) for name, executor in self._host_executors_dict.items() if multi_role in executor.roles
            ]

            if not candidates:
                self.logger.warning(f"No executors found with role {multi_role}")
                continue

            # Select first executor (sorted by name for consistency)
            selected_name, selected_executor = sorted(candidates)[0]

            # Add the ONE_* role
            selected_executor.add_role(single_role)
            self.logger.debug(f"Added {single_role} role to {selected_name}")

    def get_all_host_executors(self) -> Dict[str, NodeExecutor]:
        """
        Get all host executors.

        Returns:
            Dictionary of {node_name: NodeExecutor}
        """
        return self._host_executors_dict

    def validate_namespace_permissions(self) -> bool:
        """
        Validate that user has permissions to create pods in the configured namespace.

        This performs a dry-run check to verify permissions before attempting to create
        debug pods, providing a clear error message if permissions are insufficient.

        Returns:
            True if user has permissions

        Raises:
            RuntimeError: If user lacks permissions to create pods in the namespace
        """
        namespace = global_config.namespace
        self.logger.info(f"Validating permissions for namespace '{namespace}'...")

        with oc.timeout(30):
            result = oc.invoke("auth", ["can-i", "create", "pods", f"--namespace={namespace}"])
            output = result.out().strip()

            if output.lower() == "yes":
                self.logger.info(f"Permissions validated for namespace '{namespace}'")
                return True

            # Permission denied
            error_msg = (
                f"Insufficient permissions to create pods in namespace '{namespace}'. "
                f"Please ensure you have the required RBAC permissions or choose a different namespace."
            )
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def connect_all(self):
        """Connect to all nodes (create debug pods) in parallel."""
        self.logger.info(f"Connecting to {len(self._host_executors_dict)} nodes in parallel...")

        def connect_node(node_name, executor):
            """Connect to a single node."""
            try:
                self.logger.info(f"Connecting to {node_name}...")
                executor.connect()
                self.logger.info(f"Successfully connected to {node_name}")
                return node_name, True, None
            except Exception as e:
                self.logger.error(f"Failed to connect to {node_name}: {e}")
                return node_name, False, str(e)

        # Connect in parallel with configurable max concurrent connections
        with ThreadPoolExecutor(max_workers=global_config.max_workers) as executor:
            futures = {
                executor.submit(connect_node, node_name, node_executor): node_name
                for node_name, node_executor in self._host_executors_dict.items()
            }

            successful = 0
            failed = 0
            for future in as_completed(futures):
                node_name, success, error = future.result()
                if success:
                    successful += 1
                else:
                    failed += 1

        self.logger.info(f"Connection complete: {successful} successful, {failed} failed")

    def disconnect_all(self):
        """Disconnect from all nodes (delete debug pods)."""
        self.logger.info("Disconnecting from all nodes...")
        for node_name, executor in self._host_executors_dict.items():
            try:
                executor.close_connection()
                self.logger.debug(f"Disconnected from {node_name}")
            except Exception as e:
                self.logger.warning(f"Failed to disconnect from {node_name}: {e}")
