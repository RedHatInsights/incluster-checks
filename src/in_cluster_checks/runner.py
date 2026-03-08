"""
In-cluster check runner - coordinates rule execution across cluster nodes.

This module contains the main execution logic for running in-cluster rule checks.
It discovers domains, builds executors, runs rules, and generates reports.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict

from in_cluster_checks import global_config
from in_cluster_checks.core.data_collector_runner import DataCollectorRunner
from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.core.executor_factory import NodeExecutorFactory
from in_cluster_checks.core.printer import StructedPrinter
from in_cluster_checks.utils.enums import Status


class InClusterCheckRunner:
    """
    Runs in-cluster rule checks across cluster nodes.

    This class handles:
    - Domain discovery and instantiation
    - Node executor creation and lifecycle
    - Rule execution coordination
    - Result aggregation and formatting
    - Summary statistics
    """

    def __init__(
        self,
        debug_rule_flag: bool = False,
        debug_rule_name: str = "",
        max_workers: int = 50,
        domain_package: str = "in_cluster_checks.domains",
    ):
        """
        Initialize runner.

        Args:
            debug_rule_flag: Enable debug mode for detailed output
            debug_rule_name: Name of specific rule to run in debug mode
            max_workers: Maximum number of concurrent workers for parallel execution
            domain_package: Python package path for domain discovery
        """
        self.logger = logging.getLogger(__name__)
        self.domain_package = domain_package
        self.factory = None
        self.node_executors = None

        # Set global config so other components can access it
        global_config.set_config(
            debug_rule_flag_val=debug_rule_flag,
            debug_rule_name_val=debug_rule_name,
            max_workers_val=max_workers,
        )

    def discover_domains(self) -> Dict[str, type]:
        """
        Dynamically discover all RuleDomain classes from domains package.

        Returns:
            Dictionary of {domain_name: DomainClass}
        """
        domains = {}
        domains_package = importlib.import_module(self.domain_package)

        # Iterate through all modules in the domains package
        for importer, modname, ispkg in pkgutil.iter_modules(domains_package.__path__):
            if modname == "__init__":
                continue

            try:
                # Import the module
                module = importlib.import_module(f"{self.domain_package}.{modname}")

                # Find all RuleDomain subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, RuleDomain) and attr != RuleDomain:
                        try:
                            # Instantiate to get domain_name
                            domain_instance = attr()
                            domain_name = domain_instance.domain_name()
                            domains[domain_name] = attr
                            self.logger.debug(f"Discovered domain: {domain_name} from {modname}")
                        except Exception as e:
                            self.logger.warning(f"Failed to instantiate domain {attr_name} from {modname}: {e}")
            except Exception as e:
                self.logger.warning(f"Failed to import module {modname}: {e}")

        return domains

    def build_component_map(self, domains: Dict[str, RuleDomain]) -> Dict[str, str]:
        """
        Build component map for all rules across all domains.

        Args:
            domains: Dictionary of {domain_name: domain_instance}

        Returns:
            Dictionary of {rule_name: component_path}
        """
        rule_component_map = {}

        for domain_name, domain in domains.items():
            for rule_class in domain.get_rule_classes():
                # Get unique name without instantiation (uses class variable if available)
                rule_name = rule_class.get_unique_name_classmethod()
                if rule_name:
                    module_path = rule_class.__module__
                    component_path = f"{module_path}.{rule_class.__name__}"
                    rule_component_map[rule_name] = component_path

        return rule_component_map

    def log_summary(self, reports: list) -> None:
        """
        Log summary statistics.

        Args:
            reports: List of formatted rule results
        """

        # Count pass/fail statistics using Status enum values
        total = len(reports)
        passed = sum(1 for r in reports if r.get("status") == Status.PASSED.value)
        failed = sum(1 for r in reports if r.get("status") == Status.FAILED.value)
        warnings = sum(1 for r in reports if r.get("status") == Status.WARNING.value)
        skip = sum(1 for r in reports if r.get("status") == Status.SKIP.value)
        not_applicable = sum(1 for r in reports if r.get("status") == Status.NOT_APPLICABLE.value)

        # Errors are failures, warnings are separate status
        errors = failed

        self.logger.info("=" * 60)
        self.logger.info("In-Cluster Check Summary:")
        self.logger.info(f"  Total rules: {total}")
        self.logger.info(f"  Passed: {passed}")
        self.logger.info(f"  Failed: {failed}")
        self.logger.info(f"    Errors: {errors}")
        self.logger.info(f"    Warnings: {warnings}")
        self.logger.info(f"  Skip: {skip}")
        self.logger.info(f"  Not Applicable: {not_applicable}")
        self.logger.info("=" * 60)

    def run(self, output_path: Path) -> str:
        """
        Run complete in-cluster check workflow.

        Args:
            output_path: Full path where JSON output will be saved

        Returns:
            Path to generated JSON file
        """
        self.logger.info("Starting direct in-cluster rule checks")

        # 1. Build node executors
        self.factory = NodeExecutorFactory()
        self.node_executors = self.factory.build_host_executors()
        self.logger.info(f"Built {len(self.node_executors)} node executor(s)")

        # 2. Connect to all nodes
        self.factory.connect_all()

        try:
            # 3. Discover and instantiate domains
            available_domain_classes = self.discover_domains()
            domains = {name: domain_class() for name, domain_class in available_domain_classes.items()}
            self.logger.info(f"Running {len(domains)} in-cluster domain(s): {', '.join(domains.keys())}")

            # 4. Build component map for all rules
            rule_component_map = self.build_component_map(domains)

            # 5. Run in-cluster RuleDomains
            results = []
            for domain_name, domain in domains.items():
                self.logger.info(f"Running in-cluster domain: {domain_name}")
                domain_result = domain.verify(self.node_executors)
                results.append(domain_result)

            # Clear data collector cache after all domains complete
            DataCollectorRunner.clear_data_collector_cache()

            # 6. Aggregate and format results
            reports = StructedPrinter.format_results(results, rule_component_map)

            # 7. Generate JSON output (skip in debug mode)
            if not global_config.debug_rule_flag:
                StructedPrinter.print_to_json(reports, str(output_path))
                self.logger.info(f"In-cluster check results saved to: {output_path}")
            else:
                self.logger.info("Debug mode: JSON output disabled")

            # 8. Log summary
            self.log_summary(reports)

            return str(output_path)

        finally:
            # 10. Cleanup: disconnect from all nodes
            if self.factory:
                self.factory.disconnect_all()

            self.logger.info("Direct in-cluster rule checks completed")
