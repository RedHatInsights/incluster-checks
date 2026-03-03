"""
Command-line interface for OpenShift in-cluster health validation checks.

This module provides the main CLI entry point for running in-cluster rule checks
on OpenShift cluster nodes.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

from in_cluster_checks.runner import InClusterCheckRunner


def setup_logging(level: str) -> None:
    """
    Configure logging based on the specified level.

    Args:
        level: Logging level (INFO, DEBUG, WARNING, ERROR)
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Also set the level on the package logger
    logger = logging.getLogger("in_cluster_checks")
    logger.setLevel(numeric_level)


def check_oc_available() -> None:
    """
    Check if the oc CLI is available in the system path.

    Raises:
        SystemExit: If oc is not available (exit code 3)
    """
    if shutil.which("oc") is None:
        logger = logging.getLogger(__name__)
        logger.error("Error: 'oc' CLI is not available in the system PATH")
        logger.error("Please install the OpenShift CLI and ensure it's in your PATH")
        logger.error("Download from: https://mirror.openshift.com/pub/openshift-v4/clients/ocp/")
        sys.exit(3)


def list_domains(runner: InClusterCheckRunner) -> None:
    """
    Display available domains and their descriptions.

    Args:
        runner: InClusterCheckRunner instance

    Raises:
        SystemExit: Always exits with code 0
    """
    domains = runner.discover_domains()
    print("\nAvailable Domains:")
    print("=" * 60)
    for domain_name, domain_class in sorted(domains.items()):
        try:
            domain_instance = domain_class()
            print(f"\n  {domain_name}")
            if hasattr(domain_instance, "__doc__") and domain_instance.__doc__:
                doc = domain_instance.__doc__.strip().split("\n")[0]
                print(f"    {doc}")
        except Exception as e:
            print(f"    (Error loading domain: {e})")
    print("\n" + "=" * 60)
    print(f"Total: {len(domains)} domain(s)\n")
    sys.exit(0)


def list_rules(runner: InClusterCheckRunner) -> None:
    """
    Display available rules organized by domain.

    Args:
        runner: InClusterCheckRunner instance

    Raises:
        SystemExit: Always exits with code 0
    """
    domains = runner.discover_domains()
    print("\nAvailable Rules by Domain:")
    print("=" * 60)

    total_rules = 0
    for domain_name, domain_class in sorted(domains.items()):
        try:
            domain_instance = domain_class()
            rules = domain_instance.get_rule_classes()

            print(f"\n{domain_name} ({len(rules)} rule(s)):")

            for rule_class in sorted(rules, key=lambda r: r.get_unique_name_classmethod() or ""):
                rule_name = rule_class.get_unique_name_classmethod()
                if rule_name:
                    # Try to get title if available
                    title = "No description"
                    try:
                        rule_instance = rule_class()
                        if hasattr(rule_instance, "title") and rule_instance.title:
                            title = rule_instance.title
                    except Exception:
                        pass

                    print(f"  - {rule_name}")
                    if title != "No description":
                        print(f"      {title}")
                    total_rules += 1

        except Exception as e:
            print(f"  (Error loading domain: {e})")

    print("\n" + "=" * 60)
    print(f"Total: {total_rules} rule(s) across {len(domains)} domain(s)\n")
    sys.exit(0)


def main() -> None:
    """
    Main CLI entry point.

    Raises:
        SystemExit: Always exits with appropriate code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description="Run OpenShift in-cluster health validation checks\n\n"
        "This tool runs validation rules directly on OpenShift cluster nodes using 'oc debug'.\n"
        "You must be logged into an OpenShift cluster before running this tool.",
        prog="openshift-checks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["INFO", "DEBUG", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="./cluster-checks.json",
        help="Output file path for JSON results (default: ./cluster-checks.json)",
    )

    parser.add_argument(
        "--debug-rule",
        type=str,
        default="",
        help="Run specific rule in debug mode with full command output (no secret filtering). "
        "Specify rule unique name (e.g., 'check_disk_usage') "
        "or title (e.g., 'Check Disk Usage')",
    )

    parser.add_argument(
        "--list-domains",
        action="store_true",
        help="List all available domains and exit",
    )

    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all available rules by domain and exit",
    )

    args = parser.parse_args()

    # Setup logging
    try:
        setup_logging(args.log_level)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    logger = logging.getLogger(__name__)

    # Check if oc CLI is available (will exit with code 3 if not found)
    check_oc_available()

    # Create runner and config
    try:
        # Create runner with direct parameters
        runner = InClusterCheckRunner(
            debug_rule_flag=(args.debug_rule != ""),
            debug_rule_name=args.debug_rule,
            max_workers=50,
        )

        # Handle list commands
        if args.list_domains:
            list_domains(runner)  # Will call sys.exit(0)

        if args.list_rules:
            list_rules(runner)  # Will call sys.exit(0)

    except Exception as e:
        logger.error(f"Error initializing runner: {e}")
        if args.log_level == "DEBUG":
            logger.exception("Full traceback:")
        sys.exit(2)

    # Validate output path
    output_path = Path(args.output)
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating output directory: {e}")
        sys.exit(2)

    # Run checks
    try:
        logger.info("Starting OpenShift in-cluster health validation checks")
        logger.info(f"Output will be saved to: {output_path.absolute()}")

        if args.debug_rule:
            logger.info(f"Debug mode enabled for rule: {args.debug_rule}")
            logger.info("Secret filtering is DISABLED in debug mode")
            logger.info("JSON output is DISABLED in debug mode")

        result_path = runner.run(output_path=output_path)

        logger.info("=" * 60)
        logger.info("Checks completed successfully")
        logger.info(f"Results saved to: {result_path}")
        logger.info("=" * 60)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Error running checks: {e}")
        if args.log_level == "DEBUG":
            logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == "__main__":
    main()
