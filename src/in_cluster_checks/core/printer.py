"""
JSON output formatter for in-cluster rule results.

Adapted from support/HealthChecks/HealthCheckCommon/StructedPrinter.py
Outputs in Insights-compatible format similar to pg.json
"""

import json
import logging
from collections import OrderedDict
from typing import Any, Dict

from in_cluster_checks.utils.enums import Status
from in_cluster_checks.utils.secret_filter import SecretFilter


# ANSI color codes
class Color:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class StructedPrinter:
    """
    Format in-cluster rule results as JSON.

    Provides structured output formatting in Insights-compatible format.
    Stores results internally for HC-style ParallelRunner compatibility.
    """

    # Filter sensitive data from output (HC-style: matches encrypt_out)
    filter_secrets = True

    def __init__(self):
        """Initialize printer with empty results storage."""
        # Internal storage for HC-style pattern
        # Structure: {host_key: {validator_name: result_dict}}
        self._results = OrderedDict()

    def add_result(self, host_key: str, validator_name: str, result: Dict[str, Any]):
        """
        Add a rule result (thread-safe for parallel execution).

        Args:
            host_key: Host identifier (e.g., "node1 - 192.168.1.10")
            validator_name: Rule unique name
            result: Result dictionary with validation data
        """
        if host_key not in self._results:
            self._results[host_key] = OrderedDict()

        self._results[host_key][validator_name] = result

    def print_result(
        self,
        unique_operation_name: str,
        title_description: str,
        host_ip: str,
        host_name: str,
        bash_cmd_lines: list,
        rule_log: list,
        in_maintenance: bool,
        status: str,
        run_time: float = 0,
        exception: str = None,
        describe_msg: str = None,
        documentation_link: str = None,
        problem_type: str = None,
        node_labels: str = "",
        system_info: dict = None,
        table_headers: list = None,
        table_data: list = None,
        extra: dict = None,
    ):
        """
        Central print method (HC-style pattern).

        This method handles secret filtering for all rule results.
        All callers should use this method directly instead of wrapper methods.

        Args:
            unique_operation_name: Rule unique name
            title_description: Human-readable title
            host_ip: Host IP address
            host_name: Host name
            bash_cmd_lines: Commands executed (may contain secrets)
            rule_log: Execution log (may contain secrets)
            in_maintenance: Whether host is in maintenance mode
            status: Validation status (passed, failed, warning, info, skip, not_applicable)
            run_time: Execution time in seconds
            exception: Exception details (may contain secrets from system output)
            describe_msg: Description message
            documentation_link: Link to documentation
            problem_type: Internal problem type classification
            node_labels: Node role labels (e.g., "control-plane,worker")
            system_info: Structured data from RuleResult (e.g., Blueprint data)
            extra: Extra fields not shown in regular HTML view (e.g., html_tab, is_uniform)
        """
        # Filter sensitive data (HC pattern: matches StructedPrinter.encrypt_out)
        # Note: bash_cmd_lines and rule_log may contain secrets from system output
        # Exception filtering is done in the exception's __str__() method
        if StructedPrinter.filter_secrets:
            bash_cmd_lines = SecretFilter.filter_string_array(bash_cmd_lines)
            rule_log = SecretFilter.filter_string_array(rule_log)

        # Use host_key for internal storage (backward compatibility)
        host_key = f"{host_name} - {host_ip}"

        # Build result dictionary with separate node_name and node_ip fields
        result = {
            "node_ip": host_ip,
            "node_name": host_name,
            "node_labels": node_labels,
            "bash_cmd_lines": bash_cmd_lines,
            "rule_log": rule_log,
            "description_title": title_description,
            "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
        }

        # Add optional fields
        if problem_type is not None:
            result["problem_type"] = problem_type
        if exception is not None:
            result["exception"] = exception
        if describe_msg is not None:
            result["describe_msg"] = describe_msg
        if run_time is not None:
            result["run_time"] = run_time
        if documentation_link is not None:
            result["documentation_link"] = documentation_link
        if in_maintenance is not None:
            result["in_maintenance"] = in_maintenance
        if system_info is not None:
            result["system_info"] = system_info
        if table_headers is not None:
            result["table_headers"] = table_headers
        if table_data is not None:
            result["table_data"] = table_data
        if extra is not None:
            result["extra"] = extra

        self.add_result(host_key, unique_operation_name, result)

    def get_msg(self) -> OrderedDict:
        """
        Get all collected results (HC-style interface).

        Returns:
            OrderedDict of {host_key: {validator_name: result}}
        """
        return self._results

    @staticmethod
    def _pprinttable(rows):
        """
        Pretty-print table in ASCII format (adapted from HC's pprinttable).

        Args:
            rows: List of namedtuples with the data to print

        Returns:
            List of strings representing the formatted table
        """
        result_lines = []
        if len(rows) == 0:
            return result_lines

        headers = rows[0]._fields
        lens = []
        for i in range(len(rows[0])):
            # Calculate max length ignoring ANSI color codes
            max_len = 0
            for x in rows:
                val_str = str(x[i])
                # Remove ANSI codes for length calculation
                clean_str = val_str.replace(Color.GREEN, "").replace(Color.RED, "")
                clean_str = clean_str.replace(Color.YELLOW, "").replace(Color.BLUE, "")
                clean_str = clean_str.replace(Color.RESET, "").replace(Color.BOLD, "")
                max_len = max(max_len, len(clean_str))
            max_len = max(max_len, len(headers[i]))
            lens.append(max_len)

        hformats = []
        for i in range(len(rows[0])):
            hformats.append("%%-%ds" % lens[i])

        hpattern = " | ".join(hformats)
        separator = "-+-".join(["-" * n for n in lens])

        result_lines.append(hpattern % tuple(headers))
        result_lines.append(separator)
        for line in rows:
            # For colored output, we need to handle spacing properly
            formatted_fields = []
            for i, field in enumerate(line):
                field_str = str(field)
                # Remove ANSI codes for padding calculation
                clean_str = field_str.replace(Color.GREEN, "").replace(Color.RED, "")
                clean_str = clean_str.replace(Color.YELLOW, "").replace(Color.BLUE, "")
                clean_str = clean_str.replace(Color.RESET, "").replace(Color.BOLD, "")
                padding = lens[i] - len(clean_str)
                formatted_fields.append(field_str + " " * padding)
            result_lines.append(" | ".join(formatted_fields))
        result_lines.append(separator)
        result_lines.append("")

        return result_lines

    def print_summary(self, domain_name: str) -> None:
        """
        Print validation summary to screen after domain completes.

        Prints rule results line-by-line with colored status indicators.

        Args:
            domain_name: Name of the domain that just completed
        """
        logger = logging.getLogger(__name__)

        logger.info(f"{Color.BOLD}***********************************************************{Color.RESET}")
        logger.info(f"{Color.BOLD}{Color.BLUE}Domain: {domain_name}{Color.RESET}")
        logger.info(f"{Color.BOLD}***********************************************************{Color.RESET}")

        if not self._results:
            logger.info("-- No rules were run --")
            return

        # Print rule results for each host
        for host_key in sorted(self._results.keys()):
            logger.info("")
            logger.info(f"{Color.BOLD}AT HOST: {host_key}{Color.RESET}")
            logger.info("")

            validations = self._results[host_key]
            if not validations:
                logger.info(f"{Color.GREEN}-- all is well here --{Color.RESET}")
                continue

            # Print each validation line-by-line
            for validator_name, result in validations.items():
                title = result.get("description_title", validator_name)
                status = result.get("status", "unknown")

                # Determine status display with color
                if status == Status.PASSED.value:
                    status_str = f"{Color.GREEN}PASS{Color.RESET}"
                elif status == Status.FAILED.value:
                    status_str = f"{Color.RED}FAIL{Color.RESET}"
                elif status == Status.WARNING.value:
                    status_str = f"{Color.YELLOW}WARN{Color.RESET}"
                elif status == Status.INFO.value:
                    status_str = f"{Color.BLUE}INFO{Color.RESET}"
                elif status == Status.SKIP.value:
                    status_str = "SKIP"
                elif status == Status.NOT_APPLICABLE.value:
                    status_str = "NA"
                else:
                    status_str = status.upper()

                # Get describe message (failure description)
                describe_msg = result.get("describe_msg", "")

                # Print validation line
                logger.info(f"  [{status_str}] {title}")

                # If there's a failure message, print it indented
                if describe_msg:
                    lines = describe_msg.splitlines()
                    # If too many lines (>10), show first 5 and summarize
                    if len(lines) > 10:
                        for line in lines[:5]:
                            logger.info(f"      {line}")
                        logger.info(f"      ... ({len(lines) - 5} more similar warnings)")
                    else:
                        for line in lines:
                            # Truncate very long lines (>500 chars) for readability
                            if len(line) > 500:
                                logger.info(f"      {line[:500]}... (truncated, full details in JSON)")
                            else:
                                logger.info(f"      {line}")

            logger.info("")  # Empty line after host validations

    @staticmethod
    def print_to_json(results: Dict[str, Any], output_file: str) -> None:
        """
        Write rule results to JSON file.

        Args:
            results: Dictionary with rule results in Insights format
            output_file: Path to output JSON file
        """
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)

    @staticmethod
    def format_results(flow_results: list, rule_component_map: Dict[str, str]) -> Dict[str, Any]:
        """
        Format multiple flow results into Insights-compatible structure.

        Groups results by rule, with all host results nested in details array.
        Each rule appears once with a list of host-level results.

        Args:
            flow_results: List of flow result dictionaries
                         Each: {'domain_name': str, 'details': OrderedDict}
            rule_component_map: Map of {rule_name: full_component_path}

        Returns:
            Formatted results dictionary:
            {
                "in_cluster_rules": [
                    {
                        "rule_id": "domain|rule",
                        "component": "...",
                        "key": "rule",
                        "status": "aggregated_status",  # Worst status across all hosts
                        "description": "...",
                        "domain": "...",
                        "details": [  # Array of host results
                            {"node_ip": "...", "node_name": "...", "status": "...", ...},
                            {"node_ip": "...", "node_name": "...", "status": "...", ...}
                        ]
                    }
                ]
            }
        """
        # Build rule-grouped structure
        # Key: (domain_name, rule_name) -> Value: list of host results
        rule_groups = OrderedDict()

        for flow_result in flow_results:
            domain_name = flow_result["domain_name"]
            details = flow_result["details"]

            # Group results by rule
            for host_key, rules in details.items():
                for rule_name, result in rules.items():
                    # Create unique key for this rule
                    rule_key = (domain_name, rule_name)

                    # Initialize group if not exists
                    if rule_key not in rule_groups:
                        rule_groups[rule_key] = {
                            "domain_name": domain_name,
                            "rule_name": rule_name,
                            "description": result.get("description_title"),
                            "component": rule_component_map.get(
                                rule_name, f"in_cluster_checks.{domain_name}.{rule_name}"
                            ),
                            "host_results": [],
                        }

                    # Build host-level result
                    host_result = {
                        "node_ip": result.get("node_ip"),
                        "node_name": result.get("node_name"),
                        "node_labels": result.get("node_labels", ""),
                        "status": result.get("status", "skip"),
                        "bash_cmd_lines": result.get("bash_cmd_lines", []),
                        "rule_log": result.get("rule_log", []),
                        "timestamp": result.get("time"),
                    }

                    # Add optional fields
                    failed_msg = result.get("describe_msg")
                    if failed_msg:
                        host_result["message"] = failed_msg

                    exception = result.get("exception")
                    if exception:
                        host_result["exception"] = exception

                    problem_type = result.get("problem_type")
                    if problem_type:
                        host_result["problem_type"] = problem_type

                    if "system_info" in result:
                        host_result["system_info"] = result["system_info"]

                    if "extra" in result:
                        host_result["extra"] = result["extra"]

                    # Add to group
                    rule_groups[rule_key]["host_results"].append(host_result)

        # Convert to reports format with aggregated status
        reports = []
        for rule_key, group_data in rule_groups.items():
            domain_name, rule_name = rule_key

            # Calculate aggregated status (worst status across all hosts)
            # Priority: failed > warning > info > passed > skip > not_applicable
            status_priority = {
                Status.FAILED.value: 0,
                Status.WARNING.value: 1,
                Status.INFO.value: 2,
                Status.PASSED.value: 3,
                Status.SKIP.value: 4,
                Status.NOT_APPLICABLE.value: 5,
            }

            host_statuses = [hr["status"] for hr in group_data["host_results"]]
            aggregated_status = min(
                host_statuses,
                key=lambda s: status_priority.get(s, 99),  # Unknown statuses get lowest priority
                default=Status.SKIP.value,
            )

            report = {
                "rule_id": f"{domain_name}|{rule_name}",
                "component": group_data["component"],
                "key": rule_name,
                "status": aggregated_status,
                "description": group_data["description"],
                "domain": domain_name,
                "details": group_data["host_results"],  # Array of host results
            }

            reports.append(report)

        return reports
