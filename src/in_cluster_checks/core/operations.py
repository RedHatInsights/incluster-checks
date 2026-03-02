"""
Base classes for healthcheck operations.

Adapted from support/HealthChecks/HealthCheckCommon/operations.py
Simplified for OpenShift use case.
"""

import abc
import logging
import threading
from typing import Any

from in_cluster_checks import global_config
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.utils.file_utils import FileUtils


class Operator:
    """
    Base class for all operations that run commands on nodes or containers.

    Provides common functionality for command execution and output handling.
    """

    TIMEOUT_EXIT_CODE = 124
    TIMEOUT_KILL_EXIT_CODE = 137
    TIMEOUT_BEFORE_KILL = 60

    def __init__(self, host_executor):
        """
        Initialize operator with a host executor.

        Args:
            host_executor: NodeExecutor or ContainerExecutor instance
        """
        self._host_executor = host_executor
        self.logger = logging.getLogger(__name__)

    def get_host_ip(self) -> str:
        """Get IP address of the host this operator is running on."""
        return self._host_executor.ip

    def get_host_name(self) -> str:
        """Get name of the host this operator is running on."""
        return self._host_executor.host_name

    def get_node_labels(self) -> str:
        """Get node role labels (e.g., 'control-plane,worker')."""
        return self._host_executor.node_labels

    def run_cmd(self, cmd: str, timeout: int = 120, add_bash_timeout: bool = False) -> tuple:
        """
        Run command on host/container.

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds (default: 120)
            add_bash_timeout: If True, wraps command with bash timeout command for guaranteed termination

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        return_code, stdout, stderr = self._host_executor.execute_cmd(cmd, timeout, add_bash_timeout=add_bash_timeout)
        return return_code, stdout, stderr

    def get_output_from_run_cmd(self, cmd: str, timeout: int = 30, message: str = None) -> str:
        """
        Run command and return stdout if successful.

        Calls self.run_cmd() which subclasses can override to change execution behavior.

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds (default: 30)
            message: Optional custom error message

        Returns:
            stdout from command (stripped)

        Raises:
            UnExpectedSystemOutput: If command fails (non-zero exit code)
        """
        rc, out, err = self.run_cmd(cmd, timeout)

        if rc != 0:
            error_message = message if message else "Unexpected output (exit code: {})".format(rc)
            raise UnExpectedSystemOutput(ip=self.get_host_ip(), cmd=cmd, output=out + err, message=error_message)

        return out.strip()

    def build_cmd_error_message(self, base_msg: str, stdout: str = "", stderr: str = "") -> str:
        """
        Build a formatted error message for failed commands.

        Appends stderr and stdout to the base error message in a consistent format.
        Use this when a command fails and you want to include the command output in the error.

        Args:
            base_msg: Base error message describing what failed
            stdout: Command stdout (if any)
            stderr: Command stderr (if any)

        Returns:
            Formatted error message with stderr/stdout appended
        """
        error_msg = base_msg
        if stderr:
            error_msg += f"\nError: {stderr}"
        if stdout:
            error_msg += f"\nOutput: {stdout}"
        return error_msg

    def run_cmd_return_is_successful(self, cmd: str, timeout: int = 30) -> bool:
        """
        Run command and return True if successful (exit code 0).

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds

        Returns:
            True if command succeeded, False otherwise
        """
        return_code, _, _ = self.run_cmd(cmd, timeout)
        return return_code == 0

    def run_and_get_the_nth_field(self, cmd: str, n: int, separator: str = None, timeout: int = 30) -> str:
        """
        Run command and extract the n-th field from output.

        Args:
            cmd: Command to execute
            n: Field number to extract (1-indexed)
            separator: Field separator (default: whitespace)
            timeout: Timeout in seconds

        Returns:
            The n-th field from command output

        Raises:
            Exception: If command fails or field extraction fails
        """
        out = self.get_output_from_run_cmd(cmd, timeout)
        return self._get_the_nth_field(out, n, separator)

    @staticmethod
    def _get_the_nth_field(text: str, n: int, separator: str = None) -> str:
        """
        Extract the n-th field from text.

        Args:
            text: Input text
            n: Field number to extract (1-indexed)
            separator: Field separator (default: whitespace)

        Returns:
            The n-th field from text
        """
        if separator:
            fields = text.split(separator)
        else:
            fields = text.split()

        if n < 1 or n > len(fields):
            raise IndexError(f"Field {n} not found in text (has {len(fields)} fields)")

        return fields[n - 1]


class FlowsOperator(Operator):
    """
    Base operator for flows (validations, data collectors, etc.).

    Adds documentation and metadata support to base Operator.
    """

    # Class variable: Define where this operation should run
    # e.g., [Objectives.ALL_NODES], [Objectives.ICE_CONTAINER], etc.
    objective_hosts = []

    def __init__(self, host_executor):
        """Initialize flows operator with documentation requirements."""
        super().__init__(host_executor)
        self.set_initial_values()
        self._enforce_have_document()

        # Verify objective_hosts is defined
        if not self.__class__.objective_hosts:
            raise ValueError(
                f"objective_hosts not defined for {self.__class__.__name__}. " "Please define as class variable."
            )

        self.file_utils = FileUtils(self)

    def set_initial_values(self):
        """Initialize operation metadata fields."""
        self._bash_cmd_lines = []
        self._rule_log = []
        self._details = ""

    def _add_cmd_to_log(self, cmd: str):
        """Add command to bash_cmd_lines for tracking."""
        self._bash_cmd_lines.append(cmd)

    def _collect_cmd_info(self, cmd: str, out: str, err: str, max_line: int = 50, max_chars_in_line: int = 1000):
        """
        Log command execution details to rule_log.

        Args:
            cmd: Command that was executed
            out: Command stdout
            err: Command stderr
            max_line: Maximum lines to log from output
            max_chars_in_line: Maximum characters per line
        """
        self._rule_log.append(f"Running command: '{cmd}'")

        out_lines = out.splitlines()
        if len(out_lines) > max_line:
            num_of_loops = max_line
            self._rule_log.append(
                f"Command output is too long. Printing first {max_line} rows - "
                "run the command manually to get full output"
            )
        else:
            num_of_loops = len(out_lines)

        if num_of_loops == 1:
            self._rule_log.append(f"Command output: {out}")
        elif num_of_loops > 0:
            self._rule_log.append("Command output:")
            for i in range(0, num_of_loops):
                if len(out_lines[i]) < max_chars_in_line:
                    self._rule_log.append(f"{out_lines[i]}.")
                else:
                    self._rule_log.append("Command output is too long - will print part of the output:")
                    self._rule_log.append(f"{out_lines[i][0:max_chars_in_line]}.")

        if err:
            self._rule_log.append(f"Command error: {err}")

        self._rule_log.append("=" * 48)

    def add_to_rule_log(self, log_entry: str):
        """
        Add an entry to the rule log.

        Args:
            log_entry: Log message to add
        """
        self._rule_log.append(log_entry)

    def run_cmd(self, cmd: str, timeout: int = 120, add_bash_timeout: bool = False) -> tuple:
        """
        Run command on host/container and log it.

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds (default: 120)
            add_bash_timeout: If True, wraps command with bash timeout command for guaranteed termination

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        self._add_cmd_to_log(cmd)

        # In debug mode, print command BEFORE execution
        if global_config.config.debug_rule_flag:
            host_name = self.get_host_name()
            print(f"\n[DEBUG] Executing on {host_name}: {cmd}", flush=True)

        return_code, out, err = super().run_cmd(cmd, timeout, add_bash_timeout=add_bash_timeout)

        # Handle debug validation mode vs normal mode differently
        if global_config.config.debug_rule_flag:
            # Debug validation: print output after execution
            print(f"[DEBUG] Return code: {return_code}", flush=True)
            if out:
                print(f"[DEBUG] STDOUT:\n{out}", flush=True)
            if err:
                print(f"[DEBUG] STDERR:\n{err}", flush=True)
            print("=" * 60, flush=True)
        # Note: In normal mode, we don't log failed commands since many failures are expected
        # (e.g., prerequisite checks testing if commands exist). The JSON output contains
        # exception details when validations fail.

        return return_code, out, err

    def get_output_from_run_cmd(self, cmd: str, timeout: int = 30, message: str = None) -> str:
        """
        Run command, log it, and return stdout if successful.

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds (default: 30)
            message: Optional custom error message (unused, for HC compatibility)

        Returns:
            stdout from command

        Raises:
            Exception: If command fails (non-zero exit code)
        """
        self._add_cmd_to_log(cmd)

        # In debug mode, print command BEFORE execution
        if global_config.config.debug_rule_flag:
            host_name = self.get_host_name()
            print(f"\n[DEBUG] Executing on {host_name}: {cmd}", flush=True)

        try:
            result = super().get_output_from_run_cmd(cmd, timeout, message)

            # In debug mode, print output after execution
            if global_config.config.debug_rule_flag:
                print("[DEBUG] Return code: 0", flush=True)
                print(f"[DEBUG] STDOUT:\n{result}", flush=True)
                print("=" * 60, flush=True)

            return result
        except Exception as e:
            # In debug mode, print the exception
            if global_config.config.debug_rule_flag:
                print(f"[DEBUG] Command failed with exception: {e}", flush=True)
                print("=" * 60, flush=True)
            # Command failed - details already logged by executor
            raise

    def _enforce_have_document(self):
        """Verify that documentation fields were set as class variables."""
        if not hasattr(self.__class__, "title") or not self.__class__.title:
            raise ValueError(
                f"title not defined as class variable for {self.__class__.__name__}. "
                f"Add: title = 'Your validator description'"
            )
        if not self.unique_name:
            raise ValueError(
                f"unique_name not set for {self.__class__.__name__}. "
                f"Add as class variable: unique_name = 'your_unique_name'"
            )

    def get_unique_name(self) -> str:
        """Get unique operation name (accessible as class or instance attribute)."""
        return self.unique_name

    def get_severity(self) -> str:
        """Get severity level (HC-style interface)."""
        return self._severity if self._severity else "NA"

    def get_implication_tags(self) -> list:
        """Get implication tags (HC-style interface)."""
        return getattr(self, "_implication_tags", [])

    def get_blocking_tags(self) -> list:
        """Get blocking tags (HC-style interface)."""
        return getattr(self, "_blocking_tags", [])

    def get_bash_cmd_lines(self) -> list:
        """Get list of commands executed (HC-style interface)."""
        return self._bash_cmd_lines

    def get_rule_log(self) -> list:
        """Get validation execution log (HC-style interface)."""
        return self._rule_log

    def get_host_roles(self) -> list:
        """Get roles of the host this operator is running on (HC-style interface)."""
        roles = getattr(self._host_executor, "roles", [])
        return list(roles) if roles else []

    def get_documentation_link(self) -> str:
        """Get documentation link for this operation (HC-style interface)."""
        return getattr(self, "_documentation_link", "")

    def is_clean_cmd_info(self) -> bool:
        """
        Whether to filter sensitive command info from output (HC-style interface).

        Returns False by default (show full output).
        Subclasses can override to return True for operations handling sensitive data.
        """
        return getattr(self, "_is_clean_cmd_info", False)


class DataCollector(FlowsOperator):
    """
    Base class for data collectors.

    Data collectors gather information from nodes/containers without
    validating anything. They can be used by validators for comparison
    or analysis.
    """

    objective_hosts = []
    threadLock = threading.RLock()  # HC-style: Thread-safe access to cached data
    raise_collection_errors = True  # Raise exception if collection fails on all hosts

    def __init__(self, host_executor=None):
        """
        Initialize data collector.

        Args:
            host_executor: NodeExecutor or ContainerExecutor instance (optional for abstract usage)
        """
        if host_executor:
            super().__init__(host_executor)
        else:
            # Allow initialization without executor for class-level operations
            self._host_executor = None
            self.logger = logging.getLogger(__name__)
        self._host_exceptions_dict = {}

    def _add_cmd_to_log(self, cmd: str):
        """Add command to bash_cmd_lines with node prefix for data collectors."""
        node_name = self.get_host_name()
        prefixed_cmd = f"[{node_name}] {cmd}"
        self._bash_cmd_lines.append(prefixed_cmd)

    def add_to_rule_log(self, log_entry: str):
        """Add log entry with node prefix for data collectors."""
        node_name = self.get_host_name()
        prefixed_log = f"[{node_name}] {log_entry}"
        self._rule_log.append(prefixed_log)

    def _enforce_have_document(self):
        """Data collectors don't require full documentation."""
        pass

    def set_document(self):
        """Data collectors don't require documentation (optional)."""
        pass

    @abc.abstractmethod
    def collect_data(self, **kwargs) -> Any:
        """
        Collect data from host/container.

        Must be implemented by subclasses.

        Args:
            **kwargs: Collector-specific arguments

        Returns:
            Collected data (type depends on collector)

        Example:
            def collect_data(self, **kwargs):
                output = self.get_output_from_run_cmd("nmcli conn show bond0")
                dns_servers = self._parse_dns(output)
                return dns_servers
        """
        raise NotImplementedError(f"collect_data() must be implemented in {self.__class__.__name__}")

    @classmethod
    def format_exception_for_logging(cls, e: Exception) -> str:
        """
        Format exception with type and full message with proper indentation.

        Args:
            e: The exception to format

        Returns:
            Formatted exception string with type on first line, details indented
        """
        exc_type = type(e).__name__
        exc_msg = str(e).strip()  # Full exception message, stripped of leading/trailing whitespace

        if exc_msg:
            # Put type on first line, then indent the details
            lines = [f"{exc_type}:"]
            for line in exc_msg.split("\n"):
                lines.append(f"     {line}")  # 5 spaces to align with indent hierarchy
            return "\n".join(lines)
        else:
            return exc_type
