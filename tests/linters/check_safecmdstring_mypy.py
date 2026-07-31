#!/usr/bin/env python3
"""
Mypy wrapper that only reports SafeCmdString type violations.

This script runs mypy and filters output to only show errors related to SafeCmdString,
providing focused feedback on command injection prevention.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Run mypy and filter for SafeCmdString violations only."""
    if len(sys.argv) < 2:
        # No files provided - check all src files
        files = ["src/in_cluster_checks/"]
    else:
        files = sys.argv[1:]

    # Run mypy with minimal configuration
    cmd = [
        "mypy",
        *files,
        "--check-untyped-defs",  # Check functions without type annotations
        "--show-error-codes",    # Show error codes like [arg-type]
        "--no-error-summary",    # Don't show summary
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Filter output to only SafeCmdString-related errors
    safecmd_errors = []
    for line in result.stdout.splitlines():
        if "SafeCmdString" in line and "error:" in line:
            safecmd_errors.append(line)

    if safecmd_errors:
        print("\nFound SafeCmdString type violations:\n")
        for error in safecmd_errors:
            print(f"  {error}")
        print()
        print("Methods requiring SafeCmdString:")
        print("  - run_cmd(cmd, ...)")
        print("  - get_output_from_run_cmd(cmd, ...)")
        print("  - execute_cmd(cmd, ...)")
        print("  - run_cmd_return_is_successful(cmd, ...)")
        print("  - run_and_get_the_nth_field(cmd, ...)")
        print("  - run_rsh_cmd(namespace, pod, command, ...)")
        print()
        print("Use: SafeCmdString('cmd {var}').format(var=value)")
        print()
        sys.exit(1)
    else:
        # All SafeCmdString checks passed
        sys.exit(0)


if __name__ == "__main__":
    main()
