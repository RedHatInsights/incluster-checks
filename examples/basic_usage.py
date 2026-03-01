#!/usr/bin/env python3
"""
Basic usage example for OpenShift In-Cluster Checks.

This example demonstrates the simplest way to run in-cluster health validation checks.
"""

from pathlib import Path

from in_cluster_checks.interfaces.config import InClusterCheckConfig
from in_cluster_checks.runner import InClusterCheckRunner


def main():
    """Run basic in-cluster health checks."""
    # Create a runner with default configuration
    runner = InClusterCheckRunner()

    # Define output path
    output_path = Path("./cluster-checks.json")

    # Run checks
    print(f"Running in-cluster health checks...")
    print(f"Results will be saved to: {output_path.absolute()}")

    result_path = runner.run(output_path=output_path)

    print(f"\n✅ Checks completed successfully!")
    print(f"Results saved to: {result_path}")
    print(f"\nYou can view the results with: cat {result_path} | jq .")


if __name__ == "__main__":
    main()
