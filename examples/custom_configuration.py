#!/usr/bin/env python3
"""
Custom configuration example for OpenShift In-Cluster Checks.

This example shows how to customize the runner configuration.
"""

from pathlib import Path

from in_cluster_checks.interfaces.config import InClusterCheckConfig
from in_cluster_checks.runner import InClusterCheckRunner


def main():
    """Run checks with custom configuration."""
    # Create custom configuration
    config = InClusterCheckConfig(
        # Enable debug mode for a specific rule
        debug_rule_flag=False,
        debug_rule_name="",
        # Enable parallel execution (default: True)
        parallel_execution=True,
        # Set maximum concurrent workers
        max_workers=10,
        # Set command timeout in seconds
        command_timeout=120,
        # Enable secret filtering (default: True)
        filter_secrets=True,
    )

    # Create runner with custom config
    runner = InClusterCheckRunner(config=config)

    # Define output path
    output_path = Path("./custom-checks.json")

    # Run checks
    print("Running in-cluster health checks with custom configuration...")
    print(f"- Parallel execution: {config.parallel_execution}")
    print(f"- Max workers: {config.max_workers}")
    print(f"- Command timeout: {config.command_timeout}s")
    print(f"- Secret filtering: {config.filter_secrets}")
    print(f"\nResults will be saved to: {output_path.absolute()}")

    result_path = runner.run(output_path=output_path)

    print(f"\n✅ Checks completed successfully!")
    print(f"Results saved to: {result_path}")


if __name__ == "__main__":
    main()
