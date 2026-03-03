#!/usr/bin/env python3
"""
Custom configuration example for OpenShift In-Cluster Checks.

This example shows how to customize the runner configuration.
"""

from pathlib import Path

from in_cluster_checks.runner import InClusterCheckRunner


def main():
    """Run checks with custom configuration."""
    # Create runner with custom configuration
    runner = InClusterCheckRunner(
        # Enable debug mode for a specific rule
        debug_rule_flag=False,
        debug_rule_name="",
        # Set maximum concurrent workers (default: 50)
        max_workers=75,
    )

    # Define output path
    output_path = Path("./custom-checks.json")

    # Run checks
    print("Running in-cluster health checks with custom configuration...")
    print(f"- Max workers: 75")
    print(f"\nResults will be saved to: {output_path.absolute()}")

    result_path = runner.run(output_path=output_path)

    print(f"\n✅ Checks completed successfully!")
    print(f"Results saved to: {result_path}")


if __name__ == "__main__":
    main()
