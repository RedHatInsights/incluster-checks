"""
Parallel execution runner for rules and data collectors.

Adapted from support/HealthChecks/HealthCheckCommon/parallel_runner.py
Provides threading support for running rules across multiple hosts concurrently.
"""

import logging
import threading
import time
import traceback
from typing import Any, Callable, Dict, List

from in_cluster_checks import global_config
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives, Status


class ParallelRunner:
    """
    Parallel execution runner for rules and data collectors.

    Provides threading support to run operations concurrently across multiple hosts.
    """

    @staticmethod
    def run_in_parallel(instances: List[Any], target_func: Callable, *args, **kwargs):
        """
        Run target function in parallel for each instance using threading.

        Args:
            instances: List of instances to process
            target_func: Function to call for each instance
            *args: Additional positional arguments to pass to target_func
            **kwargs: Additional keyword arguments to pass to target_func
        """
        logger = logging.getLogger(__name__)

        if not instances:
            logger.debug("No instances to run")
            return

        thread_list = []

        # Create a thread for each instance
        for instance in instances:
            if kwargs:
                thread = threading.Thread(target=target_func, args=(instance,) + args, kwargs=kwargs)
            else:
                thread = threading.Thread(target=target_func, args=(instance,) + args)

            thread.daemon = True
            thread_list.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in thread_list:
            thread.join()

        logger.debug(f"Completed parallel execution of {len(instances)} instances")

    @staticmethod
    def run_data_collectors_in_parallel(collector_instances: List[Any], results_dict: Dict[str, Any], **kwargs):
        """
        Run data collectors in parallel and store results in results_dict (one-to-one mode).

        Args:
            collector_instances: List of data collector instances
            results_dict: Dictionary to store results {host_name: data}
            **kwargs: Arguments to pass to collect_data()
        """
        logger = logging.getLogger(__name__)

        if not collector_instances:
            logger.debug("No data collectors to run")
            return

        # Thread-safe lock for updating results_dict
        lock = threading.Lock()

        def collect_and_store(collector):
            """Collect data and store in results_dict (thread-safe)."""
            try:
                host_name = collector.get_host_name()
                data = collector.collect_data(**kwargs)

                with lock:
                    results_dict[host_name] = {
                        "data": data,
                        "bash_cmd_lines": collector.get_bash_cmd_lines(),
                        "rule_log": collector.get_rule_log(),
                        "exception": None,
                    }
            except Exception as e:
                # Store exception in results (no logging per user request)
                with lock:
                    results_dict[host_name] = {
                        "data": None,
                        "bash_cmd_lines": collector.get_bash_cmd_lines(),
                        "rule_log": collector.get_rule_log(),
                        "exception": collector.format_exception_for_logging(e),
                    }

        # Run collectors in parallel
        ParallelRunner.run_in_parallel(collector_instances, collect_and_store)

        logger.debug(f"Completed parallel execution of {len(collector_instances)} data collectors")

    @staticmethod
    def run_domain_rules_on_all_hosts(rule_groups: List[List[Any]], printer):
        """
        Run all rules in a domain on all hosts (HC-style interface).

        This follows HC's ParallelRunner.run_validation_flows_on_all_host() pattern.

        Args:
            rule_groups: List of lists of rule instances grouped by rule class
                        [[OvsRule_node1, OvsRule_node2], [BondRule_node1, BondRule_node2]]
            printer: StructedPrinter instance for collecting results
        """
        logger = logging.getLogger(__name__)
        target = ParallelRunner.run_rule_on_one_host

        # Run each group of rules (all instances of one rule class) in parallel
        for rules_list in rule_groups:
            if rules_list:
                # Get rule name from first instance
                rule_name = rules_list[0].get_unique_name()
                is_enabled = rules_list[0].is_enabled_for_active_profile()
                if is_enabled:
                    # Run all instances of this rule in parallel
                    ParallelRunner.run_operator_on_all_hosts(rules_list, target, printer)

                    # Log completion after all nodes finish for this rule
                    logger.info(f"Completed rule '{rule_name}' on all applicable nodes")
                else:
                    logger.info(f"Rule '{rule_name}' is disabled for profile '{global_config.active_profile}'")

    @staticmethod
    def run_operator_on_all_hosts(operator_list: List[Any], target: Callable, printer, **kwargs):
        """
        Run operator function on all hosts in parallel.

        Follows HC's ParallelRunner.run_operator_on_all_hosts() pattern.

        Args:
            operator_list: List of operator instances (rules or data collectors)
            target: Target function to execute for each operator
            printer: Printer for collecting results
            **kwargs: Additional arguments to pass to target
        """
        ParallelRunner.run_target_in_parallel(operator_list, target, printer, **kwargs)
        return 0

    @staticmethod
    def run_target_in_parallel(operator_list: List[Any], target: Callable, *args, **kwargs):
        """
        Execute target function in parallel for all operators.

        Follows HC's ParallelRunner.run_target_in_parallel() pattern.

        Args:
            operator_list: List of operators to execute
            target: Function to call for each operator
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
        """
        thread_list = []

        for operator_instance in operator_list:
            if kwargs:
                thread = threading.Thread(target=target, args=(operator_instance,) + args, kwargs=kwargs)
            else:
                thread = threading.Thread(target=target, args=(operator_instance,) + args)

            thread.daemon = True
            thread_list.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in thread_list:
            thread.join()

    @staticmethod
    def format_exception_for_json(e: Exception, full_trace: str) -> str:
        """
        Format exception for JSON output with clean, readable structure.

        Extracts key information from OpenShift exceptions and formats them clearly.

        Args:
            e: The exception object
            full_trace: Full traceback string

        Returns:
            Formatted exception string with key details
        """
        # Check if it's an OpenShift Python exception with extra details
        if hasattr(e, "result") and hasattr(e.result, "err"):
            # Extract the actual error message from OpenShift result
            error_lines = []
            error_lines.append(f"Error Type: {type(e).__name__}")
            error_lines.append(f"Error Message: {str(e).split(']')[0].strip('[')}")
            error_lines.append("")

            # Add the actual command error
            err_msg = e.result.err().strip()
            if err_msg:
                error_lines.append("Command Error Output:")
                error_lines.append(err_msg)
                error_lines.append("")

            # Add simplified traceback (without OpenShift client internals)
            error_lines.append("Traceback:")
            trace_lines = full_trace.split("\n")
            for line in trace_lines:
                # Skip OpenShift client internal lines and references
                if (
                    "/openshift_client/" not in line
                    and ".stack" not in line
                    and '"cmd":' not in line
                    and '"references":' not in line
                ):
                    error_lines.append(line)

            return "\n".join(error_lines)
        else:
            # Regular exception - return full trace
            return f"Error Type: {type(e).__name__}\nError Message: {str(e)}\n\n{full_trace}"

    @staticmethod
    def get_exception_str(exception: str, is_clean_cmd_info: bool) -> str:
        """
        Get exception string with secret filtering (HC-style).

        Args:
            exception: Exception details/traceback
            is_clean_cmd_info: Whether to filter sensitive information

        Returns:
            Exception string (filtered if needed)
        """
        if is_clean_cmd_info and not global_config.debug_rule_flag:
            return "** full trace is not available here for this rule **"
        return exception

    @staticmethod
    def print_exception(e: Exception, printer, hosted_rule_instance, in_maintenance: bool, is_clean_cmd_info: bool):
        """
        Classify and print exception following HC's pattern.

        Handles different exception types with specific categorization:
        - UnExpectedSystemOutput → SYS_PROBLEM
        - Others → NOT_PERFORMED

        Args:
            e: Exception that was raised
            printer: StructedPrinter instance
            hosted_rule_instance: Rule that raised exception
            in_maintenance: Whether host is in maintenance mode
            is_clean_cmd_info: Whether to filter sensitive command info
        """
        # Get raw traceback
        raw_trace = traceback.format_exc()

        # Format exception for better readability in JSON
        formatted_exception = ParallelRunner.format_exception_for_json(e, raw_trace)

        # Apply secret filtering if needed
        full_trace = ParallelRunner.get_exception_str(formatted_exception, is_clean_cmd_info)

        if isinstance(e, UnExpectedSystemOutput):
            printer.print_result(
                unique_operation_name=hosted_rule_instance.get_unique_name(),
                title_description=hosted_rule_instance.title,
                host_ip=hosted_rule_instance.get_host_ip(),
                host_name=hosted_rule_instance.get_host_name(),
                bash_cmd_lines=hosted_rule_instance.get_bash_cmd_lines(),
                rule_log=hosted_rule_instance.get_rule_log(),
                in_maintenance=in_maintenance,
                status=Status.SKIP.value,
                problem_type=Status.SYS_PROBLEM.value,
                describe_msg="Unexpected system output",
                exception=full_trace,
                documentation_link=hosted_rule_instance.get_documentation_link(),
                node_labels=hosted_rule_instance.get_node_labels(),
            )
        else:
            # Generic exception - skip status
            printer.print_result(
                unique_operation_name=hosted_rule_instance.get_unique_name(),
                title_description=hosted_rule_instance.title,
                host_ip=hosted_rule_instance.get_host_ip(),
                host_name=hosted_rule_instance.get_host_name(),
                bash_cmd_lines=hosted_rule_instance.get_bash_cmd_lines(),
                rule_log=hosted_rule_instance.get_rule_log(),
                in_maintenance=in_maintenance,
                status=Status.SKIP.value,
                problem_type="NOT_PERFORMED",
                exception=full_trace,
                describe_msg="Unexpected error (details in the .json file)",
                documentation_link=hosted_rule_instance.get_documentation_link(),
                node_labels=hosted_rule_instance.get_node_labels(),
            )

    @staticmethod
    def run_rule_on_one_host(hosted_rule_instance, printer):
        """
        Run a single rule instance and store result in printer.

        Follows HC's ParallelRunner.run_validation_on_one_host() pattern with
        full exception classification support.

        Args:
            hosted_rule_instance: Rule instance to run
            printer: StructedPrinter for storing results
        """
        logger = logging.getLogger(__name__)

        # Determine if host is in maintenance mode (HC pattern)
        host_roles = getattr(hosted_rule_instance, "get_host_roles", lambda: [])()
        in_maintenance = Objectives.MAINTENANCE in host_roles if host_roles else False

        try:
            start_time = time.time()

            # Check prerequisites first

            prerequisite_result = hosted_rule_instance.is_prerequisite_fulfilled()

            if not prerequisite_result.fulfilled:
                # Prerequisite not met - print NOT_APPLICABLE result
                end_time = time.time()
                run_time = end_time - start_time

                printer.print_result(
                    unique_operation_name=hosted_rule_instance.get_unique_name(),
                    title_description=hosted_rule_instance.title,
                    host_ip=hosted_rule_instance.get_host_ip(),
                    host_name=hosted_rule_instance.get_host_name(),
                    bash_cmd_lines=hosted_rule_instance.get_bash_cmd_lines(),
                    rule_log=hosted_rule_instance.get_rule_log(),
                    in_maintenance=in_maintenance,
                    run_time=run_time,
                    status=Status.NOT_APPLICABLE.value,
                    describe_msg=prerequisite_result.message or "Prerequisites not fulfilled",
                    documentation_link=hosted_rule_instance.get_documentation_link(),
                    node_labels=hosted_rule_instance.get_node_labels(),
                    links=hosted_rule_instance.__class__.get_links(),
                )
                return

            # Run rule
            if hasattr(hosted_rule_instance, "run_rule"):
                result = hosted_rule_instance.run_rule()
            else:
                logger.error(f"Rule {hosted_rule_instance.__class__.__name__} missing run_rule()")
                return

            end_time = time.time()
            run_time = end_time - start_time

        except Exception as e:
            # Re-raise in debug mode (HC behavior)
            if global_config.debug_rule_flag:
                raise

            # Classify and print exception using HC's pattern
            ParallelRunner.print_exception(
                e, printer, hosted_rule_instance, in_maintenance, hosted_rule_instance.is_clean_cmd_info()
            )

        else:
            # Rule completed successfully (no exception)
            # Check return value
            assert result is not None, f"Rule {hosted_rule_instance.get_unique_name()} forgot to return value"
            assert isinstance(result, RuleResult), f"Rule must return RuleResult, got {type(result)}"

            # Print result with status
            printer.print_result(
                unique_operation_name=hosted_rule_instance.get_unique_name(),
                title_description=hosted_rule_instance.title,
                host_ip=hosted_rule_instance.get_host_ip(),
                host_name=hosted_rule_instance.get_host_name(),
                bash_cmd_lines=hosted_rule_instance.get_bash_cmd_lines(),
                rule_log=hosted_rule_instance.get_rule_log(),
                in_maintenance=in_maintenance,
                run_time=run_time,
                status=result.status.value,
                describe_msg=result.message,
                documentation_link=hosted_rule_instance.get_documentation_link(),
                node_labels=hosted_rule_instance.get_node_labels(),
                system_info=result.system_info,  # Add structured data
                table_headers=result.table_headers,  # Add table headers
                table_data=result.table_data,  # Add table data
                extra=result.extra,  # Add custom fields
                links=hosted_rule_instance.__class__.get_links(),
            )
