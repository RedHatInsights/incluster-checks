"""
Node executor for running healthcheck commands.

Provides execution environment for healthcheck validations:
- NodeExecutor: Runs commands on cluster nodes via persistent debug pods

Adapted from support OpenshiftHostExecutor.
Uses openshift_client library for pod management and command execution.
"""

import atexit
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager

try:
    import openshift_client as oc
except ImportError:
    # Will be handled at runtime if NodeExecutor is used
    oc = None

from in_cluster_checks.core.exceptions import HostNotReachable, UnExpectedSystemOutput
from in_cluster_checks.utils.enums import ORCHESTRATOR_HOST_IP, ORCHESTRATOR_HOST_NAME, Objectives


def _add_bash_timeout(cmd: str, timeout: int, timeout_kill_after_seconds: int = 60) -> str:
    """Wrap command with bash timeout command for guaranteed termination."""
    timeout_prefix = f"timeout --kill-after={timeout_kill_after_seconds}s {timeout}s"
    # Handle sudo commands specially
    if cmd.startswith("sudo "):
        return f"sudo {timeout_prefix} {cmd[5:]}"
    return f"{timeout_prefix} {cmd}"


def _configure_oc_logging():
    """
    Configure openshift_client logging based on OpenShift's debug mode.

    The openshift_client library can produce verbose output when commands fail.
    This function sets the appropriate logging level based on whether we're in debug mode.
    In non-debug mode: Set to ERROR to suppress verbose error dumps
    In debug mode: Set to DEBUG to show all details for troubleshooting
    """
    # Check if we're in debug mode by examining the root logger's effective level
    root_logger = logging.getLogger()
    is_debug = root_logger.getEffectiveLevel() <= logging.DEBUG

    # Configure openshift_client logger
    oc_logger = logging.getLogger("openshift_client")
    if is_debug:
        oc_logger.setLevel(logging.DEBUG)
    else:
        # Suppress verbose error output in non-debug mode
        oc_logger.setLevel(logging.ERROR)


@contextmanager
def suppress_oc_logging():
    """
    Context manager to temporarily silence openshift_client logging.

    Used during prerequisite checks to prevent verbose error logs when
    commands are expected to fail (e.g., checking if tools are installed).

    Example:
        with suppress_oc_logging():
            # Commands here won't trigger verbose oc logging
            rc, out, err = executor.execute_cmd("which ipmitool")
    """
    oc_logger = logging.getLogger("openshift_client")
    original_level = oc_logger.level

    try:
        # Temporarily raise log level to CRITICAL to suppress all output
        oc_logger.setLevel(logging.CRITICAL)
        yield
    finally:
        # Restore original log level
        oc_logger.setLevel(original_level)


class NodeExecutor:
    """
    Execute commands on OpenShift cluster nodes using persistent debug pods.

    Creates a debug pod on the node (using `oc debug node/<name>`) and
    reuses it for multiple command executions via `oc rsh`.

    Based on support's OpenshiftHostExecutor.
    """

    def __init__(
        self, node_name: str, node_ip: str, roles: list = None, node_labels: str = "", namespace: str = "default"
    ):
        """
        Initialize node executor.

        Args:
            node_name: Name of the OpenShift node
            node_ip: IP address of the node
            roles: List of Objectives (roles) for this node (e.g., [Objectives.MASTERS, Objectives.ALL_NODES])
            node_labels: String with node role labels (e.g., "master,worker" or "control-plane")
            namespace: Namespace to create debug pod in (default: default)
        """
        if oc is None:
            raise ImportError("openshift_client library is required for NodeExecutor")

        # Configure openshift_client logging based on debug mode
        _configure_oc_logging()

        self.node_name = node_name
        self.ip = node_ip
        self.host_name = node_name
        self.roles = roles if roles is not None else []
        self.node_labels = node_labels
        self.namespace = namespace
        self.logger = logging.getLogger(__name__)
        self.is_local = False
        self.is_connected = False
        self._pod_id = None
        self._connection_error_details = ""
        self._threadLock = threading.Lock()

    def connect(self):
        """
        Create persistent debug pod on the node.

        This creates a debug pod that will be reused for all commands.
        The pod is automatically deleted when the executor is destroyed.
        """
        if self.is_connected or self.is_local:
            return

        self._generate_debug_pod()

        if self._pod_id:
            self.is_connected = True
            self.logger.info(f"Debug pod created for node {self.node_name}: {self._pod_id}")
            # Register cleanup handler
            atexit.register(self.close_connection)
        else:
            self.logger.error(f"Failed to create debug pod for {self.node_name}: {self._connection_error_details}")
            raise HostNotReachable(
                self.node_name, "Cannot create oc debug pod to the node", details=self._connection_error_details
            )

    def _generate_debug_pod(self):
        """
        Generate and create the debug pod using openshift_client.

        Adapted from support's generate_debug_pod method.
        """
        # Generate unique pod ID
        pod_id = f"{self.node_name}-debug-{uuid.uuid4().hex[:8]}"

        try:
            with oc.timeout(60 * 3):  # 3 minute timeout (was 30 minutes)
                # Get debug pod spec using `oc debug` - explicitly specify namespace
                result = oc.invoke("debug", [f"node/{self.node_name}", "-o", "json", f"--namespace={self.namespace}"])
                json_pod = json.loads(result.out())

                # Modify pod metadata
                json_pod["metadata"]["name"] = pod_id
                json_pod["metadata"]["namespace"] = self.namespace

                # Create the pod
                oc.create(json.dumps(json_pod))

            # Wait for pod to be ready
            time.sleep(5)  # Increased from 2 to 5 seconds to ensure pod is ready

            self._pod_id = pod_id
            self.logger.debug(f"Created debug pod {pod_id} for node {self.node_name}")

        except Exception as e:
            self._connection_error_details = f"Exception creating debug pod: {str(e)}"
            self.logger.error(f"Failed to create debug pod for {self.node_name}: {e}")

    def _run_rsh_cmd(self, cmd: str, timeout: int = 120):
        """
        Run command in debug pod using `oc rsh`.

        Args:
            cmd: Command to execute (will be wrapped in chroot /host)
            timeout: Timeout in seconds

        Returns:
            Result object from openshift_client with .status(), .out(), .err() methods
        """
        with oc.timeout(timeout):
            with oc.project(self.namespace):
                result = oc.invoke(
                    "rsh",
                    cmd_args=[self._pod_id, "bash", "-c", f"chroot /host {cmd}"],
                    auto_raise=False,  # Don't raise exception on non-zero exit codes
                )
        return result

    def execute_cmd(
        self,
        cmd: str,
        timeout: int = 120,
        get_not_ascii: bool = False,
        suppress_errors: bool = False,
        add_bash_timeout: bool = False,
    ) -> tuple:
        """
        Execute command on node using persistent debug pod.

        Args:
            cmd: Command to execute on the node
            timeout: Timeout in seconds (default: 120)
            get_not_ascii: Not used, kept for interface compatibility
            suppress_errors: If True, suppress verbose openshift_client error logging (used for prerequisite checks)
            add_bash_timeout: If True, wraps command with bash timeout for guaranteed termination

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        if add_bash_timeout:
            cmd = _add_bash_timeout(cmd, timeout)

        with self._threadLock:
            if not self.is_connected:
                self.connect()

            if suppress_errors:
                with suppress_oc_logging():
                    return self._execute_cmd_internal(cmd, timeout)
            else:
                return self._execute_cmd_internal(cmd, timeout)

    def _execute_cmd_internal(self, cmd: str, timeout: int) -> tuple:
        """
        Internal method to execute command (extracted for suppress_errors context manager).

        Args:
            cmd: Command to execute on the node
            timeout: Timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        # Execute command
        try:
            result = self._run_rsh_cmd(cmd, timeout)
            return result.status(), result.out(), result.err()

        except Exception as e:
            # Check if it's a pod-not-found error - try to reconnect
            error_str = str(e)
            if "Error from server (NotFound)" in error_str or "unable to upgrade connection" in error_str:
                self.logger.warning(f"Pod disappeared, attempting reconnect: {e}")
                self.reconnect()

                if not self.is_connected:
                    raise HostNotReachable(
                        self.node_name,
                        "Cannot execute command - debug pod not available after reconnect",
                        details=self._connection_error_details,
                    )

                # Retry command after reconnect
                result = self._run_rsh_cmd(cmd, timeout)
                return result.status(), result.out(), result.err()
            else:
                # Other exception (timeout, connection error, etc.) - re-raise
                raise

    def reconnect(self):
        """Reconnect to node by recreating debug pod."""
        self.close_connection()
        self.is_connected = False
        self._pod_id = None
        self.connect()

    def get_output_from_run_cmd(self, cmd: str, timeout: int = 30, message: str = "Unexpected output") -> str:
        """
        Execute command and return stdout if successful.

        NOTE: This is a simple wrapper for backward compatibility with tests.
        In production, Operator.get_output_from_run_cmd() should be used instead
        as it includes proper logging and debug support.

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds (default: 30)
            message: Error message if command fails

        Returns:
            stdout from command (stripped of trailing whitespace)

        Raises:
            UnExpectedSystemOutput: If command returns non-zero exit code
        """
        return_code, out, err = self.execute_cmd(cmd, timeout)

        if return_code == 0:
            return out.strip()
        else:
            # Command failed
            error_output = out + err
            if not out and not err:
                message = "No output from command. Command may have timed out."

            raise UnExpectedSystemOutput(
                ip=self.ip, cmd=cmd, output=error_output, message=f"{message} (exit code: {return_code})"
            )

    def close_connection(self):
        """Delete the debug pod."""
        if not self.is_local and self._pod_id:
            try:
                with oc.timeout(60):
                    with oc.project(self.namespace):
                        # Find pod by name and delete it
                        pod_obj = list(filter(lambda p: p.name() == self._pod_id, oc.get_pods_by_node(self.node_name)))[
                            0
                        ]
                        # Force delete debug pods (they may be stuck/orphaned)
                        # Using grace_period=0 immediately removes from API server
                        oc.delete(pod_obj, cmd_args=["--grace-period=0", "--force"])

                self.logger.info(f"Deleted debug pod {self._pod_id} for node {self.node_name}")
            except Exception as e:
                self.logger.warning(f"Failed to delete debug pod {self._pod_id}: {e}")
            finally:
                self.is_connected = False
                self._pod_id = None

    def get_host_name(self) -> str:
        """Get node name."""
        return self.node_name

    def get_host_ip(self) -> str:
        """Get node IP address."""
        return self.ip

    def add_role(self, role: str):
        """
        Add a role to this executor.

        Used by factory to assign ONE_* roles to selected executors.

        Args:
            role: Role to add (e.g., Objectives.ONE_MASTER)
        """
        if role not in self.roles:
            self.roles.append(role)


class OrchestratorExecutor:
    """
    Executor for orchestrator-level operations running in Pendrive container.

    Not a real cluster node - represents the Pendrive container itself.
    Cannot run node commands - use run_oc_command() or run_rsh_cmd() for pod access.
    """

    def __init__(self):
        """Initialize orchestrator executor."""
        self.node_name = ORCHESTRATOR_HOST_NAME
        self.host_name = ORCHESTRATOR_HOST_NAME
        self.ip = ORCHESTRATOR_HOST_IP
        self.roles = [Objectives.ORCHESTRATOR]
        self.node_labels = ""  # No node labels (orchestrator is not a real node)
        self.is_local = True
        self.is_connected = True  # No connection needed
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """No-op - orchestrator doesn't connect to anything."""
        pass

    def execute_cmd(self, cmd: str, timeout: int = 120, **kwargs) -> tuple:
        """
        Orchestrator cannot execute node commands.

        Raises:
            NotImplementedError: Always - use run_oc_command() or run_rsh_cmd() instead
        """
        raise NotImplementedError(
            f"execute_cmd('{cmd}') is not available for orchestrator-level operations. "
            "Orchestrator operations cannot run node commands. "
            "Use run_oc_command() to run oc commands, or run_rsh_cmd() to execute in pods."
        )

    def close_connection(self):
        """No-op - no connection to close."""
        pass
