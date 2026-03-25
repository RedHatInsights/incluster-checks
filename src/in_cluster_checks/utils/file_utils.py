"""
File utilities for in-cluster checks.

Adapted from support/HealthChecks/HealthCheckCommon/file_utils.py
Only includes functions needed by in-cluster validation framework.
"""

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class FileUtils:
    """Utility class for file operations."""

    def __init__(self, operator):
        """
        Initialize FileUtils with an operator.

        Args:
            operator: Rule or FlowsOperator instance that provides run_cmd() method
        """
        self.operator = operator

    def read_file(self, path):
        """
        Read file contents with error handling.

        Args:
            path: Path to the file to read

        Returns:
            str: File contents

        Raises:
            UnExpectedSystemOutput: If file cannot be read
        """
        cmd = SafeCmdString("cat {path}").format(path=path)
        return_code, out, err = self.operator.run_cmd(cmd)
        if return_code != 0:
            error = f"Problem reading the file {path}:\n{err}"
            raise UnExpectedSystemOutput(self.operator.get_host_ip(), str(cmd), error)
        return out

    def is_file_exist(self, file_path):
        """
        Check if a file exists.

        Args:
            file_path: Path to check

        Returns:
            bool: True if file exists, False otherwise
        """
        cmd = SafeCmdString("ls {file_path}").format(file_path=file_path)
        return_code, _, _ = self.operator.run_cmd(cmd)
        return return_code == 0

    def get_lines_in_file(self, file_path):
        """
        Get file contents as list of lines.

        Args:
            file_path: Path to the file

        Returns:
            list: List of lines, or None if file cannot be read
        """
        cmd = SafeCmdString("cat {file_path}").format(file_path=file_path)
        return_code, out, err = self.operator.run_cmd(cmd)
        if return_code != 0:
            return None
        return out.splitlines()

    def list_files(self, pattern):
        """
        List files matching a pattern.

        Args:
            pattern: File path pattern (can include wildcards)

        Returns:
            list: List of matching file paths, or None if command fails
        """
        cmd = SafeCmdString("ls {pattern}").format(pattern=pattern)
        return_code, out, err = self.operator.run_cmd(cmd)
        if return_code != 0:
            return None
        return out.strip().split("\n") if out.strip() else []

    def list_dirs(self, pattern):
        """
        List directories matching a pattern.

        Args:
            pattern: Directory path pattern (can include wildcards)

        Returns:
            list: List of matching directory paths, or None if command fails
        """
        cmd = SafeCmdString("ls -d {pattern}").format(pattern=pattern)
        return_code, out, err = self.operator.run_cmd(cmd)
        if return_code != 0:
            return None
        return out.strip().split("\n") if out.strip() else []

    def is_dir_exist(self, dir_path):
        """
        Check if a directory exists.

        Args:
            dir_path: Directory path to check (can include wildcards)

        Returns:
            bool: True if directory exists, False otherwise
        """
        cmd = SafeCmdString("test -d {dir_path}").format(dir_path=dir_path)
        return_code, _, _ = self.operator.run_cmd(cmd)
        return return_code == 0
