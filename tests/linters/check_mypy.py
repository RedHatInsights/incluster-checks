#!/usr/bin/env python3
"""
Mypy pre-commit hook that reports all errors except non-SafeCmdString [assignment] errors.

Used as a pre-commit hook entry point (see .pre-commit-config.yaml).
Mypy configuration is read from mypy.ini.
"""

import subprocess
import sys


def main() -> None:
    """Run mypy and report all errors, filtering [assignment] to SafeCmdString only."""
    files = sys.argv[1:] if len(sys.argv) > 1 else ["src/in_cluster_checks/"]

    cmd = ["mypy", *files]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode not in (0, 1):
        print(result.stderr or result.stdout)
        sys.exit(result.returncode)

    errors = []
    has_safecmd_errors = False
    for line in result.stdout.splitlines():
        if "error:" not in line:
            continue
        if "[assignment]" in line and "SafeCmdString" not in line:
            continue
        errors.append(line)
        if "SafeCmdString" in line:
            has_safecmd_errors = True

    if not errors:
        sys.exit(0)

    for error in errors:
        print(error)

    if has_safecmd_errors:
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


if __name__ == "__main__":
    main()
