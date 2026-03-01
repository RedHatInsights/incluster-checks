#!/usr/bin/env python3
"""
Custom domain example for OpenShift In-Cluster Checks.

This example demonstrates how to create a custom domain with custom rules.
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.core.rule import Rule


# First, define custom rules (or import from custom_rule.py)
class ExampleCustomRule(Rule):
    """Example custom rule for the custom domain."""

    objective_hosts = [Rule.Objectives.ALL_NODES]

    def set_document(self):
        self.unique_name = "example_custom_check"
        self.title = "Example custom validation check"

    def run_rule(self):
        """Simple example that always passes."""
        return_code, stdout, stderr = self.run_cmd("echo 'Custom check passed'")
        return Rule.RuleResult.passed("Custom validation check passed")


# Define the custom domain
class CustomValidationDomain(RuleDomain):
    """
    Custom domain for organization-specific validation rules.

    This domain demonstrates:
    - How to create a custom domain
    - How to add custom rules to the domain
    - How the domain integrates with the runner
    """

    def domain_name(self) -> str:
        """Return the unique name for this domain."""
        return "custom_validation"

    def get_rule_classes(self) -> List[type]:
        """Return list of rule classes in this domain."""
        return [
            ExampleCustomRule,
            # Add more custom rules here
        ]


# Example usage
if __name__ == "__main__":
    print("Custom Domain Example")
    print("=" * 60)

    # Create domain instance
    domain = CustomValidationDomain()

    print(f"Domain Name: {domain.domain_name()}")
    print(f"Number of Rules: {len(domain.get_rule_classes())}")
    print("\nRules:")
    for rule_class in domain.get_rule_classes():
        print(f"  - {rule_class.get_unique_name_classmethod()}")

    print("\nTo use this domain:")
    print("1. Save this file in a Python package (e.g., my_custom_checks/)")
    print("2. Pass the package path to InClusterCheckRunner:")
    print('   runner = InClusterCheckRunner(domain_package="my_custom_checks.domains")')
    print("3. The runner will automatically discover and execute your custom domain")
