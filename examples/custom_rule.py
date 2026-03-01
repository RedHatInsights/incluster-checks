#!/usr/bin/env python3
"""
Custom rule example for OpenShift In-Cluster Checks.

This example demonstrates how to create a custom validation rule.
"""

from in_cluster_checks.core.rule import Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives, Status


class CustomDiskCheckRule(Rule):
    """
    Example custom rule: Check if /tmp directory has enough free space.

    This rule demonstrates:
    - How to define a custom validation rule
    - How to run commands on nodes
    - How to parse command output
    - How to return pass/fail results
    """

    # Define which nodes this rule applies to
    objective_hosts = [Objectives.ALL_NODES]

    def set_document(self):
        """Set rule metadata - called during initialization."""
        self.unique_name = "custom_tmp_disk_check"
        self.title = "Verify /tmp directory has sufficient free space"

    def run_rule(self):
        """Execute the validation logic."""
        # Run command to check /tmp disk usage
        return_code, stdout, stderr = self.run_cmd("df -h /tmp | tail -1")

        if return_code != 0:
            return RuleResult.failed(
                f"Failed to check /tmp disk space: {stderr}",
                extra_data={"stderr": stderr},
            )

        # Parse df output (Filesystem, Size, Used, Avail, Use%, Mounted)
        parts = stdout.split()
        if len(parts) < 6:
            return RuleResult.failed("Unexpected df output format", extra_data={"output": stdout})

        # Get usage percentage (e.g., "45%" -> 45)
        try:
            usage_percent = int(parts[4].rstrip("%"))
        except (ValueError, IndexError):
            return RuleResult.failed("Could not parse usage percentage", extra_data={"output": stdout})

        # Check if usage is below threshold (80%)
        threshold = 80
        if usage_percent >= threshold:
            return RuleResult.failed(
                f"/tmp directory usage is {usage_percent}% (threshold: {threshold}%)",
                extra_data={"usage_percent": usage_percent, "threshold": threshold, "output": stdout},
            )

        return RuleResult.passed(
            f"/tmp directory usage is {usage_percent}% (threshold: {threshold}%)",
            extra_data={"usage_percent": usage_percent, "threshold": threshold},
        )


# Example usage
if __name__ == "__main__":
    print("Custom Rule Example")
    print("=" * 60)
    print(f"Rule Name: {CustomDiskCheckRule.get_unique_name_classmethod()}")
    print("\nTo use this rule:")
    print("1. Create a custom domain that includes this rule")
    print("2. Or add it to an existing domain's rule list")
    print("3. The runner will automatically discover and execute it")
