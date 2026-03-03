"""
Data collector execution and caching.

This module handles all data collector execution logic including:
- Cache management for many-to-one relationships
- Parallel and sequential execution
- Relationship validation
- Result aggregation and error handling
"""

import logging
from typing import Any, Dict

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.executor import OrchestratorExecutor
from in_cluster_checks.core.parallel_runner import ParallelRunner
from in_cluster_checks.utils.dict_utils import convert_dict_to_sorted_json_str
from in_cluster_checks.utils.enums import ORCHESTRATOR_HOST_NAME, Objectives


class DataCollectorRunner:
    """
    Handles data collector execution with caching for many-to-one relationships.

    Cache Implementation:
    - Cache is ONLY used for many-to-one relationships
    - When multiple source nodes collect from same target, data is cached
    - Uses tuple keys: (class_full_name, host_name, kwargs_str)
      where class_full_name is "module.path.ClassName" to prevent collisions
    - Thread-safe with double-checked locking pattern
    """

    # Class-level cache for many-to-one data collector results
    # Structure: {(class_full_name, host_name, kwargs_str): {data, exception, bash_cmd_lines, rule_log}}
    # class_full_name example: "in_cluster_checks.rules.hw.ProcessorType"
    data_collector_db = {}

    @classmethod
    def execute_data_collector(
        cls, rule_instance, collector_class: type, use_parallel: bool = True, **kwargs
    ) -> Dict[str, Any]:
        """
        Execute a DataCollector on all hosts and return aggregated results.

        Args:
            rule_instance: Rule instance (for accessing helpers and state)
            collector_class: DataCollector subclass to instantiate
            use_parallel: Whether to run collectors in parallel (default: True)
            **kwargs: Arguments to pass to collect_data()

        Returns:
            Dictionary of {hostname: collected_data}

        Example:
            dns_data = DataCollectorRunner.execute_data_collector(self, Bond0Dns)
            # dns_data = {"node1": {...}, "node2": {...}, ...}
        """
        # Validate no many-to-many relationships
        cls.validate_data_collector_relationship(
            rule_instance.objective_hosts,
            collector_class.objective_hosts,
            rule_instance.unique_name,
            collector_class.__name__,
        )

        hosts_dict = cls.get_data_collector_hosts_dict(rule_instance._node_executors, collector_class.objective_hosts)
        if not hosts_dict:
            return {}

        collector_instances = rule_instance._create_collector_instances(collector_class, hosts_dict)
        if not collector_instances:
            return {}

        results_dict = cls.run_collectors(collector_instances, use_parallel, collector_class, rule_instance, **kwargs)

        aggregated = cls.aggregate_collector_results(rule_instance, results_dict)

        cls.handle_collector_failures(rule_instance, collector_class, aggregated["host_exceptions"], hosts_dict)

        return aggregated["simple_results"]

    @classmethod
    def run_data_collector_with_cache(cls, collector_instance, results_dict, rule_instance, **kwargs):
        """
        Run data collector with caching for many-to-one relationships.

        When multiple source nodes (e.g., ALL_NODES) collect from same target
        (e.g., ONE_MASTER), cache the result to avoid redundant collection.

        Thread-safe: Uses collector's threadLock for concurrent access.

        Args:
            collector_instance: DataCollector instance
            results_dict: Dictionary to store results
            rule_instance: Rule instance (for logging which rule triggered collection)
            **kwargs: Arguments for collect_data()
        """
        # 1. Get cache lookup keys
        # Use fully qualified class name to prevent collisions between collectors
        # with same name in different modules
        class_full_name = f"{collector_instance.__class__.__module__}.{collector_instance.__class__.__name__}"
        host_name = collector_instance.get_host_name()
        kwargs_str = convert_dict_to_sorted_json_str(kwargs)
        cache_key = (class_full_name, host_name, kwargs_str)

        # 2. Track if we loaded new data (vs using cached data)
        loaded_new_data = False

        # 3. Fast path: Check cache WITHOUT lock
        if cache_key not in cls.data_collector_db:
            # 4. Cache miss: Acquire lock (collector's class-level threadLock)
            with collector_instance.threadLock:
                # 5. Double-check: Another thread may have filled cache while we waited
                if cache_key not in cls.data_collector_db:
                    # 6. Still empty: Collect data and store in cache
                    cls._load_data_collector_to_cache(collector_instance, cache_key, rule_instance, **kwargs)
                    loaded_new_data = True

            # Lock released here (exiting 'with' block)

        # 7. Retrieve from cache (guaranteed to exist now)
        cached_result = cls.data_collector_db[cache_key]
        logger = logging.getLogger(__name__)
        rule_name = rule_instance.unique_name

        # 8. Prepare rule log - add cache hit message if we used cached data (didn't load new)
        rule_log = cached_result.get("rule_log", []).copy()
        if not loaded_new_data:
            # Cache HIT: we used existing cached data instead of loading new data
            collector_class_name = collector_instance.__class__.__name__
            logger.debug(f"[CACHE] Cache HIT for {class_full_name} on {host_name} (requested by rule: {rule_name})")
            rule_log.append(f"[CACHE] Using cached {collector_class_name} data (requested by rule: {rule_name})")

        # 9. Store in results_dict (same format as non-cached execution)
        results_dict[host_name] = {
            "data": cached_result.get("data"),
            "exception": cached_result.get("exception"),
            "bash_cmd_lines": cached_result.get("bash_cmd_lines"),
            "rule_log": rule_log,
        }

    @classmethod
    def _load_data_collector_to_cache(cls, collector_instance, cache_key: tuple, rule_instance, **kwargs):
        """
        Execute data collection and store in cache with exception handling.

        Args:
            collector_instance: DataCollector instance
            cache_key: Tuple (class_full_name, host_name, kwargs_str)
                      where class_full_name is module.ClassName
            rule_instance: Rule instance (for logging which rule triggered collection)
            **kwargs: Arguments for collect_data()
        """
        logger = logging.getLogger(__name__)
        class_full_name, host_name, _ = cache_key
        rule_name = rule_instance.unique_name

        try:
            # Execute data collection
            data = collector_instance.collect_data(**kwargs)

            # Store successful result in cache
            cls.data_collector_db[cache_key] = {
                "data": data,
                "exception": None,
                "bash_cmd_lines": collector_instance.get_bash_cmd_lines(),
                "rule_log": collector_instance.get_rule_log(),
            }

            logger.debug(f"[CACHE] Cached data for {class_full_name} on {host_name} (triggered by rule: {rule_name})")

        except Exception as e:
            # Store exception in cache
            cls.data_collector_db[cache_key] = {
                "data": None,
                "exception": e,
                "bash_cmd_lines": collector_instance.get_bash_cmd_lines(),
                "rule_log": collector_instance.get_rule_log(),
            }

            logger.warning(
                f"[CACHE] Cached exception for {class_full_name} on {host_name} (triggered by rule: {rule_name}): {e}"
            )

    @classmethod
    def clear_data_collector_cache(cls):
        """
        Clear the data collector cache.

        Call this after all domains complete to free memory.
        """
        cls.data_collector_db.clear()

    @classmethod
    def run_collectors(
        cls, collector_instances: list, use_parallel: bool, collector_class: type, rule_instance, **kwargs
    ) -> Dict[str, Dict]:
        """
        Run collectors with caching for many-to-one relationships.

        Args:
            collector_instances: List of collector instances to run
            use_parallel: Whether to run in parallel
            collector_class: Collector class (for many-to-one detection)
            rule_instance: Rule instance (for relationship detection)
            **kwargs: Arguments to pass to collect_data()

        Returns:
            Dictionary of {hostname: {data, exception, bash_cmd_lines, rule_log}}
        """
        results_dict = {}
        # Determine if this is many-to-one (needs cache)
        is_many_to_one = cls.is_many_to_one_relationship(rule_instance.objective_hosts, collector_class.objective_hosts)
        if is_many_to_one:
            # Many-to-one: Use cache to avoid redundant collection
            if use_parallel and len(collector_instances) > 1:
                # Parallel execution with cache
                ParallelRunner.run_in_parallel(
                    collector_instances, cls.run_data_collector_with_cache, results_dict, rule_instance, **kwargs
                )
            else:
                # Sequential with cache
                for collector in collector_instances:
                    cls.run_data_collector_with_cache(collector, results_dict, rule_instance, **kwargs)
        else:
            # One-to-one or one-to-many: No cache needed
            if use_parallel and len(collector_instances) > 1:
                ParallelRunner.run_data_collectors_in_parallel(collector_instances, results_dict, **kwargs)
            else:
                cls.run_collectors_sequentially(collector_instances, results_dict, **kwargs)

        return results_dict

    @staticmethod
    def run_collectors_sequentially(collector_instances: list, results_dict: Dict, **kwargs):
        """
        Run collectors one by one without caching.

        Args:
            collector_instances: List of collector instances
            results_dict: Dictionary to store results
            **kwargs: Arguments for collect_data()
        """
        for collector in collector_instances:
            try:
                host_name = collector.get_host_name()
                data = collector.collect_data(**kwargs)
                results_dict[host_name] = {
                    "data": data,
                    "bash_cmd_lines": collector.get_bash_cmd_lines(),
                    "rule_log": collector.get_rule_log(),
                    "exception": None,
                }
            except Exception as e:
                host_name = collector.get_host_name()
                results_dict[host_name] = {
                    "data": None,
                    "exception": e,
                    "bash_cmd_lines": collector.get_bash_cmd_lines(),
                    "rule_log": collector.get_rule_log(),
                }

    @staticmethod
    def get_data_collector_hosts_dict(node_executors, objective_hosts):
        """
        Get host executors matching the data collector's objective_hosts.

        Uses simple role checking since ONE_* roles are added to executors
        during factory initialization (following HealthCheck pattern).

        Args:
            node_executors: Dictionary of {node_name: NodeExecutor}
            objective_hosts: List of Objectives from DataCollector

        Returns:
            Dictionary of {node_name: NodeExecutor} for matching hosts
        """
        hosts_dict = {}

        for role in objective_hosts:
            if role == Objectives.ORCHESTRATOR:
                hosts_dict[ORCHESTRATOR_HOST_NAME] = OrchestratorExecutor()
                continue

            for host_name, host_executor in node_executors.items():
                if role in host_executor.roles:
                    hosts_dict[host_name] = host_executor

        return hosts_dict

    @staticmethod
    def validate_data_collector_relationship(
        source_roles: list, target_roles: list, rule_name: str, collector_name: str
    ):
        """
        Validate that data collector does not create many-to-many relationships.

        Data collectors support:
        - one-to-one (single -> single): e.g., ONE_MASTER -> ONE_WORKER
        - many-to-one (multi -> single): e.g., ALL_NODES -> ONE_MASTER
        - one-to-many (single -> multi): e.g., ONE_MASTER -> ALL_NODES

        But NOT many-to-many (multi -> multi): e.g., ALL_NODES -> ALL_WORKERS
        This is because the cache and data aggregation logic cannot handle
        this pattern correctly.

        Args:
            source_roles: Rule's objective_hosts
            target_roles: Collector's objective_hosts
            rule_name: Rule name for error message
            collector_name: Collector name for error message

        Raises:
            AssertionError: If many-to-many relationship detected
        """
        # Check if source has any multi-type roles (not in single types)
        has_multi_source = any(role not in Objectives.get_all_single_types() for role in source_roles)

        if has_multi_source:
            # Source is multi-type, so target MUST be all single-type
            assert all(role in Objectives.get_all_single_types() for role in target_roles), (
                f"Data collector does not support many-to-many relationships. "
                f"Rule '{rule_name}' has multi-type source roles {source_roles}, "
                f"but collector '{collector_name}' has multi-type target roles {target_roles}. "
                f"When source is multi-type, target must be single-type only "
                f"(one of {Objectives.get_all_single_types()})."
            )

    @staticmethod
    def is_many_to_one_relationship(source_roles: list, target_roles: list) -> bool:
        """
        Determine if rule->collector is a many-to-one relationship (needs cache).

        A many-to-one relationship exists when:
        - Source (rule) has multi-type objectives (e.g., ALL_NODES, WORKERS)
        - Target (collector) has ONLY single-type objectives (e.g., ONE_MASTER)

        Many-to-one relationships benefit from caching because multiple source
        nodes collect from the same target node.

        Args:
            source_roles: Rule's objective_hosts
            target_roles: Collector's objective_hosts

        Returns:
            True if many-to-one (cache needed), False otherwise

        Examples:
            - ALL_NODES -> ONE_MASTER: True (many-to-one, cache)
            - ONE_MASTER -> ONE_WORKER: False (one-to-one, no cache)
            - ONE_MASTER -> ALL_NODES: False (one-to-many, no cache)
        """
        # Check if source has any multi-type roles

        has_multi_source = any(role not in Objectives.get_all_single_types() for role in source_roles)

        # Check if target has ONLY single-type roles
        has_only_single_target = all(role in Objectives.get_all_single_types() for role in target_roles)

        # Many-to-one if source is multi AND target is single-only
        return has_multi_source and has_only_single_target

    @staticmethod
    def aggregate_collector_results(rule_instance, results_dict: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Extract data and aggregate logs/exceptions.

        Args:
            rule_instance: Rule instance to update with logs and exceptions
            results_dict: Dictionary of {hostname: {data, exception, bash_cmd_lines, rule_log}}

        Returns:
            Dictionary with keys:
                - simple_results: {hostname: collected_data}
                - host_exceptions: {hostname: exception_string}
        """
        simple_results = {}
        host_exceptions = {}

        for host_name, result in results_dict.items():
            simple_results[host_name] = result["data"]

            # Aggregate command lines and logs
            rule_instance._bash_cmd_lines.extend(result["bash_cmd_lines"])
            rule_instance._rule_log.extend(result["rule_log"])
            if result["exception"]:
                rule_instance._rule_log.append(f"[{host_name}] ERROR: {result['exception']}")
                host_exceptions[host_name] = result["exception"]

        return {"simple_results": simple_results, "host_exceptions": host_exceptions}

    @staticmethod
    def handle_collector_failures(
        rule_instance, collector_class: type, host_exceptions: Dict[str, str], hosts_dict: Dict[str, Any]
    ):
        """
        Handle collector failures and track success.

        Args:
            rule_instance: Rule instance to update with exception tracking
            collector_class: Collector class that was executed
            host_exceptions: Dictionary of {hostname: exception_string}
            hosts_dict: Dictionary of {hostname: host_executor}
        """
        # Track collector exceptions
        if host_exceptions:
            rule_instance.data_collector_exceptions[collector_class.__name__] = host_exceptions

        # Check if all hosts failed
        if DataCollectorRunner.is_collector_failed_on_all_hosts(host_exceptions, hosts_dict):
            if collector_class.raise_collection_errors:
                DataCollectorRunner.raise_collection_failed_on_all_hosts(
                    collector_class.__name__, host_exceptions, hosts_dict
                )
        else:
            # Collector succeeded on at least one host
            rule_instance.any_passed_data_collector = True

    @staticmethod
    def is_collector_failed_on_all_hosts(host_exceptions_dict: Dict[str, str], hosts_dict: Dict[str, Any]) -> bool:
        """
        Check if collector failed on all hosts.

        Args:
            host_exceptions_dict: Dictionary of {hostname: exception_string}
            hosts_dict: Dictionary of {hostname: host_executor}

        Returns:
            True if all hosts failed, False otherwise
        """
        return host_exceptions_dict and set(host_exceptions_dict.keys()) == set(hosts_dict.keys())

    @staticmethod
    def format_collector_exceptions(collector_name: str, host_exceptions_dict: Dict[str, str]) -> list:
        """
        Format collector exceptions for error output.

        Args:
            collector_name: Name of the collector class
            host_exceptions_dict: Dictionary of {hostname: exception_string}

        Returns:
            List of formatted exception lines
        """
        output_lines = [f"[{collector_name}]"]
        for node_name, exception in host_exceptions_dict.items():
            output_lines.append(f"  [{node_name}]")
            # Indent each line of the exception for better readability
            for line in str(exception).split("\n"):
                output_lines.append(f"    {line}")
        output_lines.append("")  # Empty line for readability
        return output_lines

    @staticmethod
    def raise_collection_failed_on_all_hosts(
        collector_class_name: str, host_exceptions_dict: Dict[str, str], hosts_dict: Dict[str, Any]
    ):
        """
        Raise UnExpectedSystemOutput when a collector fails on all hosts.

        Args:
            collector_class_name: Name of the collector class that failed
            host_exceptions_dict: Dictionary of {hostname: exception_message}
            hosts_dict: Dictionary of {hostname: host_executor}

        Raises:
            UnExpectedSystemOutput: When collector failed on all hosts
        """
        if not DataCollectorRunner.is_collector_failed_on_all_hosts(host_exceptions_dict, hosts_dict):
            return

        failed_hosts = ", ".join(host_exceptions_dict.keys())

        # Format detailed output with collector name and each host's error
        output_lines = DataCollectorRunner.format_collector_exceptions(collector_class_name, host_exceptions_dict)

        raise UnExpectedSystemOutput(
            ip=failed_hosts,
            cmd=f"DataCollector: {collector_class_name}",
            output="\n".join(output_lines),
            message=f"Collector {collector_class_name} failed on all hosts",
        )

    @staticmethod
    def raise_if_no_collector_passed(rule_instance):
        """
        Raise exception if no data collectors passed on any host.

        Args:
            rule_instance: Rule instance with collector tracking state

        Raises:
            UnExpectedSystemOutput: If all DataCollectors failed
        """
        if not rule_instance.any_passed_data_collector:
            # Format exception details
            if rule_instance.data_collector_exceptions:
                output_lines = []
                for collector_name, host_exceptions in rule_instance.data_collector_exceptions.items():
                    output_lines.extend(
                        DataCollectorRunner.format_collector_exceptions(collector_name, host_exceptions)
                    )
                output_str = "\n".join(output_lines)
            else:
                output_str = "No exception details available"

            raise UnExpectedSystemOutput(
                ip="all_hosts",
                cmd="DataCollector execution",
                output=output_str,
                message="All DataCollectors failed - no data collected",
            )
