"""Orchestrator rule for cluster resources utilization reporting."""

import re
from typing import Any, Dict, List

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import OrchestratorDataCollector
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import format_cpu, format_memory


class NodeResourcesCollector(OrchestratorDataCollector):
    """Collect node resources, allocatable capacity, roles, schedulability, and allocated resources."""

    unique_name = "collect_node_resources"
    title = "Collect Node Resources Data"

    def collect_data(self, node_executors: Dict[str, Any] | None = None, **kwargs) -> Dict[str, Any]:
        """Collect node resources and allocated data from the cluster.

        Args:
            node_executors: Dict of {node_name: NodeExecutor} for role extraction

        Returns:
            Dict containing node resources data with allocated info: {"nodes": [...]}
        """
        node_executors = node_executors or {}
        node_objects = self.oc_api.get_all_nodes(timeout=45)

        if not node_objects:
            return {"nodes": []}

        nodes_data = []
        failed_nodes = {}
        for node_obj in node_objects:
            # Use APIObject accessors instead of converting to dict
            node_name = node_obj.name()

            # Extract roles from node_executors dict
            roles = self._extract_roles(node_name, node_executors)

            # Determine schedulability
            is_schedulable = not node_obj.model.spec.get("unschedulable", False)

            # Build base node info
            node_info = {
                "name": node_name,
                "roles": roles,
                "schedulable": is_schedulable,
                "capacity": node_obj.model.status.capacity._primitive(),
                "allocatable": node_obj.model.status.allocatable._primitive(),
                "allocated": {},
            }
            # Get allocated resources from oc describe node
            rc, out, err = self.oc_api.run_oc_command("describe", ["node", node_name], timeout=45, raise_on_error=False)

            if rc != 0:
                node_info["error"] = err
                failed_nodes[node_name] = err
                self.add_to_rule_log(f"Failed to get allocated resources for node {node_name}: {err}")
            else:
                # Parse allocated resources and add to node_info
                allocated = self._parse_allocated_resources(out)
                node_info["allocated"] = allocated
            nodes_data.append(node_info)

        if len(node_objects) == len(failed_nodes):
            output_lines = ["Failed to describe all nodes:"] + [
                f"  [{node}]: {err}" for node, err in failed_nodes.items()
            ]
            raise UnExpectedSystemOutput(
                ip=", ".join(failed_nodes.keys()),
                cmd="oc describe node",
                output="\n".join(output_lines),
                message=f"Failed to get allocated resources for all {len(failed_nodes)} nodes",
            )

        return {"nodes": nodes_data}

    def _extract_roles(self, node_name: str, node_executors: Dict[str, Any]) -> List[str]:
        """Extract node roles from node_executors dict.

        Args:
            node_name: Name of the node
            node_executors: Dict of {node_name: NodeExecutor}

        Returns:
            List of role names (e.g., ["master", "worker"])
        """
        executor = node_executors.get(node_name)
        if not executor:
            return []

        # node_labels is comma-separated string like "control-plane,worker"
        node_labels = executor.node_labels
        if not node_labels:
            return []

        return sorted(node_labels.split(","))

    def _parse_allocated_resources(self, describe_output: str) -> Dict[str, Dict[str, str]]:
        """Parse 'Allocated resources' section from oc describe node output.

        Args:
            describe_output: Full output from 'oc describe node'

        Returns:
            Dict with resource allocations, e.g.:
            {
                "cpu": {"requests": "6933m", "limits": "2660m"},
                "memory": {"requests": "25724Mi", "limits": "30212Mi"},
                ...
            }
        """
        allocated = {}

        # Find "Allocated resources:" section
        lines = describe_output.split("\n")
        in_allocated_section = False

        for line in lines:
            # Start of section
            if "Allocated resources:" in line:
                in_allocated_section = True
                continue

            # End of section (empty line or next section like "Events:")
            if in_allocated_section and (not line.strip() or line.startswith("Events:")):
                break

            # Skip header lines and separators
            if in_allocated_section and ("Resource" in line or "--------" in line or "Total limits" in line):
                continue

            # Parse resource lines: "cpu                6933m (92%)    2660m (35%)"
            #                   or: "bridge.network.kubevirt.io/br-apps  0              0"
            if in_allocated_section and line.strip():
                parsed = self._parse_resource_line(line)
                if parsed:
                    allocated[parsed["resource_name"]] = {
                        "requests": parsed["requests_value"],
                        "requests_percentage": (
                            f"{parsed['requests_pct']}%" if parsed["requests_pct"] is not None else None
                        ),
                        "limits": parsed["limits_value"],
                        "limits_percentage": f"{parsed['limits_pct']}%" if parsed["limits_pct"] is not None else None,
                    }

        return allocated

    def _parse_resource_line(self, line: str) -> Dict[str, str] | None:
        """Parse a single resource line from the allocated resources table.

        Args:
            line: Line like "cpu                6933m (92%)    2660m (35%)"
                  or "bridge.network.kubevirt.io/br-apps  0              0"

        Returns:
            Dict with keys: resource_name, requests_value, requests_pct, limits_value, limits_pct
            Returns None if parse fails
        """
        # Try pattern WITH percentages first: resource_name    value1 (percent%)    value2 (percent%)
        pattern_with_pct = r"^\s*(\S+)\s+(\S+)\s+\((\d+)%\)\s+(\S+)\s+\((\d+)%\)"
        match = re.match(pattern_with_pct, line)

        if match:
            return {
                "resource_name": match.group(1),
                "requests_value": match.group(2),
                "requests_pct": match.group(3),
                "limits_value": match.group(4),
                "limits_pct": match.group(5),
            }

        # Try pattern WITHOUT percentages: resource_name    value1    value2
        pattern_no_pct = r"^\s*(\S+)\s+(\S+)\s+(\S+)\s*$"
        match = re.match(pattern_no_pct, line)

        if match:
            return {
                "resource_name": match.group(1),
                "requests_value": match.group(2),
                "requests_pct": None,  # No percentage available
                "limits_value": match.group(3),
                "limits_pct": None,  # No percentage available
            }

        return None


class ResourcesUtilization(OrchestratorRule):
    """Orchestrate resources utilization data collection and generate aggregated reporting."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "resources_utilization"
    title = "Resources Utilization"
    links = ["https://github.com/RedHatInsights/incluster-checks/wiki/Resources-%E2%80%90-Resources-Utilization"]

    # Core resources always shown (supports regex patterns)
    CORE_RESOURCES = [
        "cpu",
        "memory",
        "ephemeral-storage",
        r"hugepages-.*",  # All hugepages variants (hugepages-1Gi, hugepages-2Mi, etc.)
    ]

    def run_rule(self) -> RuleResult:
        """Coordinate collectors and aggregate resources utilization data.

        Returns:
            RuleResult with INFO status containing system_info with aggregated metrics.
        """
        # Run merged collector (combines capacity/allocatable and allocated resources)
        node_data = self.run_data_collector(NodeResourcesCollector, node_executors=self._node_executors)

        # Extract data from wrapped collector result
        # Collector returns: {'in-cluster-orchestrator': {'nodes': [...]}}
        # We need to unwrap the first (and only) value
        nodes = list(node_data.values())[0].get("nodes", []) if node_data else []

        # Aggregate resources by node
        aggregated_nodes = self._aggregate_node_data(nodes)

        # Build resources utilization data structure
        resources_utilization_data = {
            "nodes": aggregated_nodes,
        }

        message = self._build_message(aggregated_nodes, nodes)

        # Return INFO with resources_utilization_data in extra field (following Blueprint pattern)
        # All **extra kwargs become fields in result.extra dict
        return RuleResult.info(
            message=message,
            resources_utilization_data=resources_utilization_data,  # Resources health data for special tab
            html_tab="resources_utilization",  # Hint for HTML report generator
            is_uniform=True,  # Quick check for uniform config
        )

    def _aggregate_node_data(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate node resource data with allocated requests/limits.

        Args:
            nodes: List of node data from merged NodeResourcesCollector
                   (includes capacity, allocatable, and allocated in each node)

        Returns:
            List of nodes with core_resources and extended_resources
        """
        aggregated = []
        for node in nodes:
            node_name = node["name"]
            node_allocated = node.get("allocated", {})

            # Build all resource info
            all_resources = self._build_all_resources(node, node_allocated)

            # Separate into core and extended resources
            core_resources = {}
            extended_resources = {}
            for resource_name, resource_info in all_resources.items():
                if self._is_core_resource(resource_name):
                    core_resources[resource_name] = resource_info
                else:
                    extended_resources[resource_name] = resource_info

            # Build aggregated node dict
            aggregated_node = {
                "name": node_name,
                "roles": node["roles"],
                "schedulable": node["schedulable"],
                "core_resources": core_resources,
            }

            # Only add extended_resources if not empty
            if extended_resources:
                aggregated_node["extended_resources"] = extended_resources

            aggregated.append(aggregated_node)

        return aggregated

    def _is_core_resource(self, resource_name: str) -> bool:
        """Check if resource matches any core resource pattern.

        Args:
            resource_name: Name of resource to check

        Returns:
            True if resource matches any pattern in CORE_RESOURCES
        """
        for pattern in self.CORE_RESOURCES:
            if re.fullmatch(pattern, resource_name):
                return True
        return False

    def _build_all_resources(self, node: Dict[str, Any], allocated: Dict[str, Dict[str, str]]) -> Dict[str, Dict]:
        """Build resource info for all resources on the node.

        Args:
            node: Node data with capacity and allocatable
            allocated: Allocated resources from oc describe node (pre-calculated by Kubernetes)

        Returns:
            Dict mapping resource_name to resource_info
        """
        all_resources = {}

        for resource_name in node.get("capacity", {}).keys():
            if resource_name == "pods":
                continue

            resource_info = self._build_resource_info(resource_name, node, allocated)
            all_resources[resource_name] = resource_info

        return all_resources

    def _build_resource_info(
        self,
        resource_name: str,
        node: Dict[str, Any],
        allocated: Dict[str, Dict[str, str]],
    ) -> Dict[str, Any]:
        """Build resource info dict with requests/limits and percentages.

        Args:
            resource_name: Name of resource (cpu, memory, etc.)
            node: Node data with capacity and allocatable
            allocated: Allocated resources from oc describe (contains values and percentages)

        Returns:
            Resource info dict with capacity, allocatable, requests, limits, and percentages
        """
        capacity_raw = node["capacity"][resource_name]
        allocatable_raw = node["allocatable"][resource_name]

        resource_info = {
            "capacity": self._format_resource_value(capacity_raw, resource_name),
            "allocatable": self._format_resource_value(allocatable_raw, resource_name),
        }

        # Get allocated data for this resource (from oc describe)
        resource_allocated = allocated.get(resource_name, {})

        # Add requests and limits (show "---" if no allocated data)
        resource_info["requests"] = self._build_allocation_info(resource_allocated, "requests", resource_name)
        resource_info["limits"] = self._build_allocation_info(resource_allocated, "limits", resource_name)

        return resource_info

    def _build_allocation_info(
        self, resource_allocated: Dict[str, str], allocation_type: str, resource_name: str
    ) -> Dict[str, str]:
        """Build allocation info dict (requests or limits) with percentage and utilization level.

        Args:
            resource_allocated: Allocated resources for a specific resource
            allocation_type: Either "requests" or "limits"
            resource_name: Name of resource (for formatting)

        Returns:
            Dict with allocated value (with percentage if available) and utilization_level (only when percentage exists)
            Example: {"allocated": "2.9Gi (19%)", "utilization_level": "low"}
                 or: {"allocated": "0"}
        """
        if not resource_allocated or allocation_type not in resource_allocated:
            return {
                "allocated": "---",
            }

        value = resource_allocated[allocation_type]
        percentage = resource_allocated.get(f"{allocation_type}_percentage")

        # Format value to human-readable
        formatted_value = self._format_resource_value(value, resource_name)

        # Combine value and percentage into single field
        result = {}
        if percentage is None:
            result["allocated"] = formatted_value
        else:
            result["allocated"] = f"{formatted_value} ({percentage})"
            result["utilization_level"] = self._get_utilization_level(percentage)

        return result

    def _add_unit_if_missing(self, value: str, resource_name: str) -> str:
        """Add unit suffix only if completely missing (preserve Kubernetes' original format).

        Args:
            value: Resource value from Kubernetes API (e.g., "8", "7500m", "32866396Ki", "191655242229")
            resource_name: Name of resource type

        Returns:
            Value with unit added if missing (e.g., "8 cores", "191655242229B")
        """
        # Already has unit? Keep it unchanged
        units = ["Ki", "Mi", "Gi", "Ti", "K", "M", "G", "T", "m", "cores", "B"]
        if any(value.endswith(u) for u in units):
            return value

        # Add appropriate unit based on resource type
        if resource_name == "cpu":
            return f"{value} cores"
        elif resource_name in ["memory", "ephemeral-storage"] or "hugepages" in resource_name:
            return f"{value}B"
        else:
            return value

    def _format_resource_value(self, value: str, resource_name: str) -> str:
        """Format resource value to human-readable format (1-4 digits).

        Args:
            value: Raw resource value from Kubernetes API
            resource_name: Name of resource type

        Returns:
            Human-readable formatted value (e.g., "8 cores", "503Gi", "24Gi")
        """
        value_with_unit = self._add_unit_if_missing(value, resource_name)

        if resource_name == "cpu":
            return format_cpu(value_with_unit)
        elif resource_name in ["memory", "ephemeral-storage"] or "hugepages" in resource_name:
            return format_memory(value_with_unit)
        else:
            return value_with_unit

    def _get_utilization_level(self, percentage_str: str) -> str:
        """Determine utilization level based on percentage.

        Args:
            percentage_str: Percentage string (e.g., "35.4%", "92.1%")

        Returns:
            Utilization level: "low" (< 50%), "medium" (50-74%), "high" (≥ 75%)
        """
        # Parse percentage value (remove '%' and convert to float)
        try:
            percentage = float(percentage_str.rstrip("%"))
        except (ValueError, AttributeError):
            return "unknown"

        if percentage < 50:
            return "low"
        elif percentage < 75:
            return "medium"
        else:
            return "high"

    def _build_message(self, aggregated_nodes: List[Dict[str, Any]], nodes: List[Dict[str, Any]]) -> str:
        """Build result message with utilization summary and failure details.

        Args:
            aggregated_nodes: List of aggregated node data with core_resources and extended_resources
            nodes: Original node data from collector (may include errors)

        Returns:
            Formatted message string
        """
        total_nodes = len(aggregated_nodes)

        # Collect high utilization details for both core and extended resources
        high_util_details = []
        for node in aggregated_nodes:
            # Check both core_resources and extended_resources
            for resource_category in ["core_resources", "extended_resources"]:
                resources = node.get(resource_category, {})
                for resource_name, resource_info in resources.items():
                    # Check all keys in resource_info (requests, limits, etc.)
                    for key, value in resource_info.items():
                        if isinstance(value, dict) and value.get("utilization_level") == "high":
                            high_util_details.append(
                                {
                                    "node": node["name"],
                                    "resource": resource_name,
                                    "type": key,
                                    "allocated": value.get("allocated", "N/A"),
                                }
                            )

        # Build base message with utilization summary
        if high_util_details:
            high_util_nodes = len(set(d["node"] for d in high_util_details))
            details_str = "\n".join(
                f"{d['node']}: {d['resource']} {d['type']} at {d['allocated']}" for d in high_util_details
            )
            message = (
                f"Resources utilization: {total_nodes} nodes, "
                f"{high_util_nodes} node(s) with high utilization:\n"
                f"{details_str}"
            )
        else:
            message = f"Resources utilization: {total_nodes} nodes, healthy utilization levels"

        # Append failure details if any nodes failed during oc describe
        failed_nodes = [node["name"] for node in nodes if node.get("error")]
        if failed_nodes:
            failed_list = ", ".join(failed_nodes)
            message += f".\nFailed to get allocated resources (oc describe) for: {failed_list}"

        return message
