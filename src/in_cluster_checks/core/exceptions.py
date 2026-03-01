"""
Exceptions for healthcheck validations.

Adapted from support/HealthChecks/tools/Exceptions.py
Matches HC's exception hierarchy for proper exception classification.
"""

from in_cluster_checks.utils.secret_filter import SecretFilter


class ExecutionException(Exception):
    """Base exception for command execution failures."""

    pass


class UnExpectedSystemOutput(ExecutionException):
    """Exception raised when command produces unexpected output or fails."""

    def __init__(
        self, ip: str, cmd: str, output: str, message: str = "Unexpected command output", full_trace: str = ""
    ):
        """
        Initialize exception.

        Args:
            ip: Host IP address where command was executed
            cmd: Command that failed
            output: Command output (stdout + stderr)
            message: Error message describing the failure
            full_trace: Full exception traceback (optional)
        """
        self.ip = ip
        self.cmd = cmd
        self.output = output
        self.message = message
        self.full_trace = full_trace

        # Sanitize command before including in exception message
        safe_cmd = SecretFilter.sanitize(cmd)
        super().__init__(f"{message} on {ip}: {safe_cmd}\nOutput: {output[:500]}")  # Limit output length

    def __str__(self):
        """Return formatted exception string (HC-style)."""
        # Filter cmd and output together so context-aware filtering works
        # (e.g., if cmd asks for password, output will also be filtered)
        combined = f"Command: {self.cmd}\nOutput: {self.output}"
        safe_combined = SecretFilter.sanitize(combined)

        return f"\n-IP: {self.ip}\n" f"-{safe_combined}\n" f"-Message: {self.message}\n" f"-Trace: {self.full_trace}"


class UnExpectedSystemTimeOut(UnExpectedSystemOutput):
    """Exception raised when command times out."""

    def __init__(
        self,
        ip: str,
        cmd: str,
        timeout: int,
        output: str = "",
        message: str = "Command timed out",
        exited_from: str = "timeout",
        full_trace: str = "",
    ):
        """
        Initialize timeout exception.

        Args:
            ip: Host IP address
            cmd: Command that timed out
            timeout: Timeout value in seconds
            output: Partial output before timeout
            message: Error message
            exited_from: Description of timeout source
            full_trace: Full exception traceback (optional)
        """
        if exited_from:
            message += f". Exited from {exited_from}."

        super().__init__(ip, cmd, output, message, full_trace)
        self.timeout = timeout

    def __str__(self):
        """Return formatted exception string with timeout info."""
        return super().__str__() + f"\n-Timeout: {self.timeout}s"


class HostNotReachable(ExecutionException):
    """Exception raised when host/node is not reachable."""

    def __init__(self, host: str, message: str = "Host is not reachable", details: str = ""):
        """
        Initialize host unreachable exception.

        Args:
            host: Host name or IP
            message: Error message
            details: Additional details about the failure
        """
        self.host = host
        self.message = message
        self.details = details
        super().__init__(f"Host not reachable: {host} - {message}. {details}")

    def __str__(self):
        """Return formatted exception string (HC-style)."""
        return f"\nHost: {self.host}: {self.message} - {self.details}"
