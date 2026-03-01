"""
Tests for exception classes.
"""

import pytest

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput, UnExpectedSystemTimeOut


class TestUnExpectedSystemOutput:
    """Test UnExpectedSystemOutput exception."""

    def test_exception_filters_password_in_command_and_output(self):
        """Test that password in command causes output to be filtered."""
        # Command with password should filter both cmd and output
        exception = UnExpectedSystemOutput(
            ip="192.168.1.1",
            cmd="mysql -u root -p mysecretpassword",
            output="mysecretpassword",
            message="Command failed"
        )

        result = str(exception)

        # Should filter both command and output when password keyword present
        assert "[REDACTED]" in result
        assert "mysecretpassword" not in result
        assert "192.168.1.1" in result
        assert "Command failed" in result

    def test_exception_filters_token_in_command_and_output(self):
        """Test that Bearer token in command causes output to be filtered."""
        exception = UnExpectedSystemOutput(
            ip="192.168.1.1",
            cmd="curl -H 'Authorization: Bearer abc123token456' https://api.example.com",
            output='{"token": "abc123token456"}',
            message="API call failed"
        )

        result = str(exception)

        # Should filter both command and output when token present
        assert "[REDACTED]" in result
        assert "abc123token456" not in result
        assert "192.168.1.1" in result
        assert "API call failed" in result

    def test_exception_does_not_filter_normal_command(self):
        """Test that normal commands without secrets are not filtered."""
        exception = UnExpectedSystemOutput(
            ip="192.168.1.1",
            cmd="ls -la /tmp",
            output="total 100\ndrwxr-xr-x 5 root root",
            message="Command failed"
        )

        result = str(exception)

        # Should NOT filter normal commands
        assert "ls -la /tmp" in result
        assert "total 100" in result
        assert "drwxr-xr-x 5 root root" in result
        assert "[REDACTED]" not in result

    def test_exception_filters_base64_encoded_secrets(self):
        """Test that base64 encoded secrets are filtered."""
        exception = UnExpectedSystemOutput(
            ip="192.168.1.1",
            cmd="echo bXlzZWNyZXRwYXNz | base64 -d",
            output="mysecretpass",
            message="Decode failed"
        )

        result = str(exception)

        # Should filter commands with base64 decode pattern
        assert "[REDACTED]" in result
        assert "bXlzZWNyZXRwYXNz" not in result

    def test_exception_preserves_ip_and_message(self):
        """Test that IP and message are always preserved."""
        exception = UnExpectedSystemOutput(
            ip="10.0.0.5",
            cmd="secret-command --password=secret123",
            output="secret123",
            message="Authentication failed"
        )

        result = str(exception)

        # IP and message should always be present
        assert "10.0.0.5" in result
        assert "Authentication failed" in result

    def test_exception_includes_trace_field(self):
        """Test that trace field is included in output."""
        exception = UnExpectedSystemOutput(
            ip="192.168.1.1",
            cmd="test command",
            output="test output",
            message="Test error",
            full_trace="Test traceback"
        )

        result = str(exception)

        # Should include trace
        assert "Test traceback" in result
        assert "-Trace:" in result


class TestUnExpectedSystemTimeOut:
    """Test UnExpectedSystemTimeOut exception."""

    def test_timeout_exception_inherits_filtering(self):
        """Test that timeout exception also filters sensitive data."""
        exception = UnExpectedSystemTimeOut(
            ip="192.168.1.1",
            cmd="mysql -u root -p mysecretpassword",
            timeout=30,
            output="mysecretpassword",
            message="Command timed out"
        )

        result = str(exception)

        # Should filter like parent class
        assert "[REDACTED]" in result
        assert "mysecretpassword" not in result
        assert "30s" in result  # Timeout value should be shown

    def test_timeout_exception_includes_timeout_value(self):
        """Test that timeout value is included."""
        exception = UnExpectedSystemTimeOut(
            ip="192.168.1.1",
            cmd="ls -la",
            timeout=60,
            output="",
            message="Timed out"
        )

        result = str(exception)

        # Should include timeout
        assert "60s" in result
