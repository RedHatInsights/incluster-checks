"""
Base classes for Blueprint-style hardware validation.

Provides infrastructure for comparing hardware/firmware configurations
across nodes within the same host groups.
"""

import abc
import json
from collections import OrderedDict
from typing import Any, Dict, List

from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives


class HwFwDataCollector(DataCollector):
    """
    Base class for blueprint-style data collectors.

    Blueprint data collectors gather hardware/firmware information from nodes
    and organize it by component IDs (e.g., "nic_0", "socket_1", "disk_sda").

    Key features:
    - Component-based data organization
    - Command output caching to avoid duplicate executions
    - Standardized output format: {component_id: {property: value}}
    """

    # Class-level cache shared across all collector instances
    # Structure: {(node_name, command): output}
    cached_command_outputs = {}
    raise_collection_errors = False

    def __init__(self, host_executor=None):
        """
        Initialize blueprint data collector.

        Args:
            host_executor: NodeExecutor instance (optional for class-level operations)
        """
        super().__init__(host_executor)

    @abc.abstractmethod
    def get_component_ids(self) -> List[str]:
        """
        Get list of component IDs on this host.

        Component IDs identify individual hardware components for comparison.
        Examples:
        - Network interfaces: ["nic_0", "nic_1", "nic_2"]
        - CPU sockets: ["socket_0", "socket_1"]
        - Disks: ["sda", "sdb", "nvme0n1"]
        - NUMA nodes: ["numa_0", "numa_1"]

        Uses self._host_executor to query the node.

        Returns:
            List of component ID strings
        """
        raise NotImplementedError(f"get_component_ids() must be implemented in {self.__class__.__name__}")

    @abc.abstractmethod
    def get_objective_name(self) -> str:
        """
        Get objective name for this data collector.

        The objective name describes what hardware aspect is being collected.
        Format: "Component@property" or just "Component"

        Examples:
        - "Network Interface@vendor"
        - "Processor@type"
        - "Memory@size"
        - "Disk@model"

        Returns:
            Objective name string
        """
        raise NotImplementedError(f"get_objective_name() must be implemented in {self.__class__.__name__}")

    @abc.abstractmethod
    def collect_data(self, **kwargs) -> Dict[str, Dict[str, Any]]:
        """
        Collect blueprint data from host.

        Must return a dictionary mapping component IDs to their properties.

        Returns:
            Dictionary structure: {
                component_id: {
                    property_name: value,
                    ...
                },
                ...
            }

        Example return value for NetworkInterface@vendor:
            {
                "nic_0": {
                    "vendor": "Intel",
                    "model": "X710",
                    "speed": "10G"
                },
                "nic_1": {
                    "vendor": "Mellanox",
                    "model": "ConnectX-5",
                    "speed": "25G"
                }
            }
        """
        raise NotImplementedError(f"collect_data() must be implemented in {self.__class__.__name__}")

    def _run_cached_command(self, cmd: str, timeout: int = 30, ignore_errors: bool = False) -> str:
        """
        Run command with caching to avoid duplicate executions.

        If the same command was already run on this node, return cached output.
        Thread-safe for parallel execution.

        Args:
            cmd: Command to execute
            timeout: Command timeout in seconds
            ignore_errors: If True, return stdout even if command fails (non-zero exit)

        Returns:
            Command stdout

        Raises:
            Exception: If command fails and ignore_errors is False
        """
        node_name = self.get_host_name()
        cache_key = (node_name, cmd)

        # Check cache first (thread-safe)
        with self.threadLock:
            if cache_key in self.cached_command_outputs:
                self.add_to_rule_log(f"Using cached output for command: {cmd}")
                return self.cached_command_outputs[cache_key]

        # Command not cached - execute it
        if ignore_errors:
            # Use run_cmd to get raw output even on error
            _, output, _ = self.run_cmd(cmd, timeout)
        else:
            # Use get_output_from_run_cmd which raises on error
            output = self.get_output_from_run_cmd(cmd, timeout)

        # Store in cache (thread-safe)
        with self.threadLock:
            self.cached_command_outputs[cache_key] = output

        return output

    @classmethod
    def clear_cache(cls):
        """
        Clear the command output cache.

        Should be called between domain executions to free memory.
        Thread-safe.
        """
        with cls.threadLock:
            cls.cached_command_outputs.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache metrics:
            - total_entries: Total number of cached commands
            - node_count: Number of unique nodes in cache
        """
        with self.threadLock:
            total_entries = len(self.cached_command_outputs)
            unique_nodes = len(set(node for node, _ in self.cached_command_outputs.keys()))

        return {"total_entries": total_entries, "node_count": unique_nodes}


class HwFwRule(OrchestratorRule):
    """
    Base class for blueprint-style validators that compare nodes within groups.

    Blueprint validators:
    1. Collect data from all nodes using HwFwDataCollectors
    2. Group nodes by role (MASTERS, WORKERS, etc.)
    3. Compare data within each group to check uniformity
    4. Return results showing which groups are uniform vs mixed

    This class extends OrchestratorRule because it runs centrally and
    coordinates data collection across all nodes.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]

    @abc.abstractmethod
    def get_data_collectors(self) -> List[type]:
        """
        Return list of HwFwDataCollector classes to run.

        Returns:
            List of HwFwDataCollector subclasses
        """
        raise NotImplementedError(f"get_data_collectors() must be implemented in {self.__class__.__name__}")

    @abc.abstractmethod
    def get_data_category_key(self) -> str:
        """
        Get the key name for storing collected data in blueprint structure.

        Returns:
            String key: "hardware" for HardwareDetailsRule, "firmware" for FirmwareDetailsRule
        """
        raise NotImplementedError(f"get_data_category_key() must be implemented in {self.__class__.__name__}")

    def compare_within_groups(self, collected_data: Dict, node_groups: Dict) -> RuleResult:
        """
        Compare data within each node group.

        Args:
            collected_data: Data from all collectors, structure:
                {
                    collector_name: {
                        node_name: {component_id: {property: value}}
                    }
                }
            node_groups: Nodes grouped by role, structure:
                {
                    "MASTERS": [executor1, executor2],
                    "WORKERS": [executor3, executor4, executor5]
                }

        Returns:
            RuleResult with comparison status and details
        """
        # Get the category key from child class ("hardware" or "firmware")
        category_key = self.get_data_category_key()

        # Build structured result similar to HealthChecks Blueprint
        result_data = OrderedDict()

        # Process each node group
        for group_label, executors in node_groups.items():
            group_result = OrderedDict()
            group_result["node_count"] = len(executors)
            group_result["nodes"] = [e.node_name for e in executors]
            group_result[category_key] = OrderedDict()

            # Process each data collector's results for this group
            for collector_class in self.get_data_collectors():
                collector_name = collector_class.__name__
                node_data = collected_data.get(collector_name, {})

                # Parse objective name (e.g., "Processor@type" -> topic="Processor", name="type")
                objective_name = collector_class().get_objective_name()
                topic, name = self._parse_objective_name(objective_name)

                # Get data for nodes in this group
                group_data = {}
                for executor in executors:
                    data = node_data.get(executor.node_name)
                    if data:
                        group_data[executor.node_name] = data

                if not group_data:
                    continue

                # Check uniformity (returns bool)
                is_uniform = self._check_group_uniformity(group_data)

                collector_result = {
                    "is_uniform": is_uniform,  # Boolean value
                }

                if is_uniform:
                    # All nodes have same config - show representative value
                    first_node = next(iter(group_data.keys()))
                    collector_result["value"] = group_data[first_node]
                else:
                    # Mixed config - show per-node values in HC format
                    # HC format: list of {component_id: {hostname: value}}
                    collector_result["value"] = self._get_list_of_id_host_name_data(group_data)

                # Create nested structure: topic -> name -> result (HC Blueprint format)
                if topic not in group_result[category_key]:
                    group_result[category_key][topic] = OrderedDict()
                group_result[category_key][topic][name] = collector_result

            result_data[group_label] = group_result

        # Build summary message (check nested topic -> name structure)
        all_uniform = all(
            prop_info["is_uniform"]
            for group_info in result_data.values()
            for topic_data in group_info[category_key].values()
            for prop_info in topic_data.values()
        )

        if all_uniform:
            summary_msg = f"All node groups have uniform {category_key} configuration"
        else:
            summary_msg = f"Mixed {category_key} configurations detected - see 'HW & FW' tab for details"

        # Log detailed summary (nested topic -> name structure)
        self.add_to_rule_log(f"Blueprint {category_key.title()} Summary:")
        for group_label, group_info in result_data.items():
            self.add_to_rule_log(f"  Group '{group_label}': {group_info['node_count']} node(s)")
            for topic, topic_data in group_info[category_key].items():
                for name, prop_info in topic_data.items():
                    status = "Uniform" if prop_info["is_uniform"] else "Mixed"
                    self.add_to_rule_log(f"    {topic}@{name}: {status}")

        # Return INFO with structured data in extra (not shown in regular HTML view)
        # Convert OrderedDict to dict recursively for JSON serialization
        blueprint_data = json.loads(json.dumps(result_data))

        return RuleResult.info(
            message=summary_msg,
            blueprint_data=blueprint_data,  # Blueprint data for special tab
            html_tab="blueprint",  # Hint for HTML report generator
            is_uniform=all_uniform,  # Quick check for uniform config
        )

    def _group_nodes_by_labels(self, node_executors_dict: Dict) -> Dict[str, List]:
        """
        Group nodes by their node labels.

        Nodes with identical label sets are grouped together for comparison.
        This naturally handles mixed configurations (e.g., some workers have
        additional labels).

        Args:
            node_executors_dict: Dictionary of {node_name: NodeExecutor}

        Returns:
            Dictionary of {label_group: [list of NodeExecutors]}
            Example: {
                "control-plane,worker": [executor1, executor2, executor3],
                "worker": [executor4, executor5],
                "worker,app-worker": [executor6]
            }
        """
        groups = {}

        for node_name, executor in node_executors_dict.items():
            # Group by exact label string
            label_key = executor.node_labels if executor.node_labels else "no-labels"

            if label_key not in groups:
                groups[label_key] = []
            groups[label_key].append(executor)

        return groups

    def _is_uniform_within_group(self, values_dict: Dict[str, Any]) -> tuple:
        """
        Check if all nodes in group have identical values.

        Args:
            values_dict: Dictionary of {node_name: value}

        Returns:
            Tuple of (is_uniform: bool, unique_values: dict)
            - is_uniform: True if all values are identical
            - unique_values: {value: [list of nodes with this value]}
        """
        if not values_dict:
            return True, {}

        # Group nodes by their value
        value_to_nodes = {}
        for node, value in values_dict.items():
            # Convert to string for comparison (handles complex types)
            value_str = str(value)
            if value_str not in value_to_nodes:
                value_to_nodes[value_str] = []
            value_to_nodes[value_str].append(node)

        # Uniform if only one unique value
        is_uniform = len(value_to_nodes) == 1

        return is_uniform, value_to_nodes

    def _collect_all_data(self, node_groups: Dict[str, List]) -> Dict:
        """
        Run all data collectors on all nodes, organized by group.

        Args:
            node_groups: Nodes grouped by role

        Returns:
            Dictionary structure: {
                collector_class_name: {
                    node_name: collected_data
                }
            }
        """
        all_data = {}

        # Get all node executors (flatten groups)
        all_executors = {}
        for group_name, executors in node_groups.items():
            for executor in executors:
                all_executors[executor.node_name] = executor

        # Run each data collector
        for collector_class in self.get_data_collectors():
            collector_name = collector_class.__name__

            # Use run_data_collector() from Rule base class
            # This properly handles collector instantiation and data collection
            # Returns: {node_name: collected_data}
            collected = self.run_data_collector(collector_class)

            # Handle failed collections (None data) - replace with "---" placeholders
            # Following HealthChecks pattern from BlueprintValidations._collected_data()
            for node_name, data in collected.items():
                if data is None:
                    # Data collector raised exception
                    # Get component IDs to create proper "---" structure
                    executor = all_executors.get(node_name)
                    if executor:
                        try:
                            temp_collector = collector_class(host_executor=executor)
                            try:
                                component_ids = temp_collector.get_component_ids()
                            except Exception as e:
                                self.add_to_rule_log(f"Error getting component IDs for {node_name}: {e}")
                                component_ids = []
                            # Create dict with "---" for each component
                            collected[node_name] = {comp_id: "---" for comp_id in component_ids}
                        except Exception:
                            # If we can't get component IDs, use empty dict
                            collected[node_name] = {}

            # Store results
            all_data[collector_name] = collected

        self.raise_if_no_collector_passed()
        return all_data

    def _parse_objective_name(self, objective_name: str) -> tuple:
        """
        Parse objective name into topic and name.

        HC Blueprint format uses "topic@name" (e.g., "Processor@type", "Bios@version").

        Args:
            objective_name: String in format "topic@name"

        Returns:
            Tuple of (topic, name)

        Example:
            "Processor@type" -> ("Processor", "type")
            "Bios@version" -> ("Bios", "version")
        """
        parts = objective_name.split("@")
        assert len(parts) == 2 and "" not in parts, f"Expected format 'topic@name', got: {objective_name}"
        topic, name = parts
        return topic, name

    def _check_group_uniformity(self, group_data: Dict) -> bool:
        """
        Check if all nodes in group have identical hardware/firmware data.

        For hardware/firmware validation, we require strict uniformity:
        all nodes must have the exact same components with the same values.
        Different component counts (e.g., 2 disks vs 3 disks) are considered non-uniform.

        Args:
            group_data: {node_name: {component_id: value}}

        Returns:
            True if all nodes have identical data (same components and values)
        """
        if not group_data or len(group_data) == 1:
            return True

        # Convert all data to strings for comparison
        # This ensures nodes must have identical component sets and values
        data_strings = [str(sorted(data.items())) for data in group_data.values()]

        # Check if all are identical
        return len(set(data_strings)) == 1

    def _get_list_of_id_host_name_data(self, group_data: Dict) -> List[Dict]:
        """
        Convert group data to HC Blueprint format for non-uniform values.

        HC format: list of {component_id: {hostname: value}}

        Args:
            group_data: {node_name: {component_id: value}}

        Returns:
            List of dicts, one per node, mapping component_id to {hostname: value}

        Example:
            Input: {
                "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "worker-1": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"}
            }
            Output: [
                {"CPU0": {"worker-0": "Intel Xeon Gold 6238"}, "CPU1": {"worker-0": "Intel Xeon Gold 6238"}},
                {"CPU0": {"worker-1": "Intel Xeon Gold 6230"}, "CPU1": {"worker-1": "Intel Xeon Gold 6230"}}
            ]
        """
        result = []

        for host_name, id_to_data_dict in group_data.items():
            id_to_hostname_data_dict = {}
            if id_to_data_dict is not None:
                for component_id, data in id_to_data_dict.items():
                    id_to_hostname_data_dict[component_id] = {host_name: data}
            result.append(id_to_hostname_data_dict)

        return result
