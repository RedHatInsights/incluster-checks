"""
Whereabouts IPAM validations for OpenShift clusters.

Whereabouts is a CNI IPAM plugin that assigns IP addresses dynamically across a cluster.
These validators check for common issues with Whereabouts IP allocations, including:
- Duplicate IP addresses
- Missing pod references in allocations
- Missing allocations for active pods
- Mismatched allocations

Ported from: support/HealthChecks/flows/Network/network_validations.py
Original classes: WhereaboutsConfiguration, WhereaboutsDuplicateIPAddresses,
                 WhereaboutsMissingPodrefs, WhereaboutsMissingAllocations,
                 WhereaboutsExistingAllocations
"""

import copy
import ipaddress
import json
from typing import Dict, List

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives


class WhereaboutsBaseRule(OrchestratorRule):
    """
    Base class for Whereabouts IPAM validation rules.

    Provides common data collection and parsing methods used by multiple
    Whereabouts validators. Child classes inherit these methods and implement
    their own run_rule() logic.

    This follows the healthcheck pattern where validators inherit from a base class
    rather than using composition with a helper class.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if Whereabouts IPPools exist with allocations in the cluster.

        Returns:
            PrerequisiteResult indicating if Whereabouts is in use with active allocations
        """
        ippool_allocation_list = self.get_ippool_allocation_list()
        if not ippool_allocation_list:
            return PrerequisiteResult.not_met("No Whereabouts IPPool allocations found - Whereabouts is not in use")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Must be implemented by child classes.

        Raises:
            NotImplementedError: If not overridden by child class
        """
        raise NotImplementedError(f"run_rule() must be implemented by {self.__class__.__name__}")

    def gather_net_attach_def_configs(self) -> List[Dict]:
        """Gather all NetworkAttachmentDefinition configurations across all namespaces.

        Returns:
            List of dicts containing name, namespace, and config for each net-attach-def
            Example: [{'name': 'macvlan-conf', 'namespace': 'default', 'config': {...}}]
        """
        # Get all NetworkAttachmentDefinitions across all namespaces
        net_attach_defs = self.oc_api.select_resources(
            "network-attachment-definitions", timeout=120, all_namespaces=True
        )

        net_attach_def_configs = []
        for nad in net_attach_defs:
            nad_dict = nad.as_dict()

            # Extract API-guaranteed fields - KeyError here indicates API corruption
            try:
                name = nad_dict["metadata"]["name"]
                namespace = nad_dict["metadata"]["namespace"]
            except KeyError as e:
                raise UnExpectedSystemOutput(
                    ip="cluster-api",
                    cmd="oc.selector('network-attachment-definitions')",
                    output=str(nad_dict),
                    message=f"NetworkAttachmentDefinition missing required metadata field: {e}",
                )

            config_str = nad_dict.get("spec", {}).get("config", "")
            if config_str:
                try:
                    config = json.loads(config_str)
                    net_attach_def_configs.append({"name": name, "namespace": namespace, "config": config})
                except json.JSONDecodeError as e:
                    # Malformed config in cluster resource is unexpected system state
                    raise UnExpectedSystemOutput(
                        ip="cluster-api",
                        cmd="get_net_attach_def_configs",
                        output=config_str,
                        message=f"NetworkAttachmentDefinition {namespace}/{name} has malformed JSON in "
                        f"spec.config: {e}",
                    )

        return net_attach_def_configs

    def gather_ippool_configs(self) -> List[Dict]:
        """Gather all IPPool configurations across all namespaces.

        Returns:
            List of dicts containing name, namespace, and spec for each ippool
            Example: [{'name': 'whereabouts-ippool', 'namespace': 'default', 'spec': {...}}]
        """
        # Get all IPPools across all namespaces
        ippools = self.oc_api.select_resources("ippools", timeout=120, all_namespaces=True)

        ippool_configs = []
        for ippool in ippools:
            ippool_dict = ippool.as_dict()

            # Extract API-guaranteed fields - KeyError here indicates API corruption
            try:
                name = ippool_dict["metadata"]["name"]
                namespace = ippool_dict["metadata"]["namespace"]
            except KeyError as e:
                raise UnExpectedSystemOutput(
                    ip="cluster-api",
                    cmd="oc.selector('ippools')",
                    output=str(ippool_dict),
                    message=f"IPPool missing required metadata field: {e}",
                )

            ippool_configs.append({"name": name, "namespace": namespace, "spec": ippool_dict.get("spec", {})})

        return ippool_configs

    def get_net_attach_def_whereabouts_list(self) -> List[Dict]:
        """
        Get list of NetworkAttachmentDefinitions that use Whereabouts IPAM.

        Returns:
            List of dicts with name and namespace for net-attach-defs using Whereabouts
            Example: [{'name': 'macvlan-conf', 'namespace': 'default'}]
        """
        net_attach_def_configs = self.gather_net_attach_def_configs()
        temp_whereabouts_list = []

        for net_attach_def in net_attach_def_configs:
            config = net_attach_def["config"]

            # Check if ipam.type is whereabouts at top level
            if "ipam" in config and "type" in config["ipam"] and "whereabouts" in config["ipam"]["type"]:
                temp_whereabouts_list.append({"name": net_attach_def["name"], "namespace": net_attach_def["namespace"]})

                # Also add the name from inside the config if different
                if "name" in config:
                    config_name = json.dumps(config["name"]).strip('"')
                    temp_whereabouts_list.append({"name": config_name, "namespace": net_attach_def["namespace"]})

            # Check if whereabouts is in plugins array
            if "plugins" in config:
                for plugin in config["plugins"]:
                    if "ipam" in plugin and "type" in plugin["ipam"] and "whereabouts" in plugin["ipam"]["type"]:
                        temp_whereabouts_list.append(
                            {"name": net_attach_def["name"], "namespace": net_attach_def["namespace"]}
                        )
                        if "name" in config:
                            config_name = json.dumps(config["name"]).strip('"')
                            temp_whereabouts_list.append(
                                {"name": config_name, "namespace": net_attach_def["namespace"]}
                            )

        # Remove duplicates
        return self._remove_duplicate_list_items(temp_whereabouts_list)

    def gather_pod_configs(self) -> List[Dict]:
        """
        Gather pod network configurations for pods with network-status annotation.

        Uses JSONPath for efficient server-side filtering, reducing network traffic
        and improving performance in large clusters.

        Returns:
            List of dicts containing name, namespace, and network status for each pod
            Example: [{'name': 'mypod', 'namespace': 'default', 'network': [...]}]
        """
        annotation_key = "k8s.v1.cni.cncf.io/network-status"

        # Escape dots for JSONPath syntax
        escaped_key = annotation_key.replace(".", r"\.")

        # Build JSONPath query to filter pods with annotation and extract fields
        jsonpath = (
            "{range .items[?(@.metadata.annotations."
            f"{escaped_key}"
            ")]}"
            "{.metadata.name}||"
            "{.metadata.namespace}||"
            f"{{.metadata.annotations.{escaped_key}}}||"
            "{end}"
        )

        # Execute server-side query using run_oc_command
        cmd_args = ["pod", "-A", "-o", f"jsonpath={jsonpath}"]
        rc, output, err = self.oc_api.run_oc_command("get", cmd_args, timeout=120)

        # Parse output (split by delimiter)
        delimiter = "||"
        if output and output.strip():
            results = [entry for entry in output.split(delimiter) if entry.strip()]
        else:
            results = []

        # Parse results (grouped by 3: name, namespace, network-status)
        pod_configs = []
        for i in range(0, len(results), 3):
            if i + 2 < len(results):
                pod_name = results[i]
                pod_namespace = results[i + 1]
                network_json = results[i + 2]

                try:
                    network = json.loads(network_json)
                    pod_configs.append({"name": pod_name, "namespace": pod_namespace, "network": network})
                except json.JSONDecodeError as e:
                    # Network-status is system-generated by CNI - malformed JSON is unexpected
                    raise UnExpectedSystemOutput(
                        ip="cluster-api",
                        cmd=f"JSONPath query for {annotation_key}",
                        output=network_json,
                        message=f"Pod {pod_namespace}/{pod_name} has malformed network-status annotation: {e}",
                    )

        return pod_configs

    def get_pod_whereabouts_ip_list(self) -> List[Dict]:
        """
        Get list of pods using Whereabouts IPAM with their assigned IPs.

        Returns:
            List of dicts containing pod name, namespace, and IP list
            Example: [{'name': 'mypod', 'namespace': 'default', 'ips': ['10.244.0.5']}]
        """
        # Get pod configurations (returns list directly)
        pod_configs = self.gather_pod_configs()

        net_attach_def_whereabouts_list = self.get_net_attach_def_whereabouts_list()

        pod_whereabouts_ip_list = []

        for pod in pod_configs:
            for pod_network in pod["network"]:
                for net_attach_def in net_attach_def_whereabouts_list:
                    # Match by namespace/name format
                    if pod_network.get("name") == net_attach_def["namespace"] + "/" + net_attach_def["name"]:
                        pod_whereabouts_ip_list.append(
                            {"name": pod["name"], "namespace": pod["namespace"], "ips": pod_network.get("ips", [])}
                        )

        return pod_whereabouts_ip_list

    def get_ippool_allocation_list(self) -> List[Dict]:
        """
        Get list of all IP allocations from IPPools.

        Returns:
            List of dicts containing allocation details
            Example: [{'name': 'ippool-1', 'range': '10.0.0.0/24',
                      'allocation_number': '5', 'allocation_data': {...}}]
        """
        ippool_configs = self.gather_ippool_configs()
        ippool_allocation_list = []

        for ippool in ippool_configs:
            if "allocations" not in ippool["spec"]:
                continue

            allocations = ippool["spec"]["allocations"]
            for allocation_number, allocation_data in allocations.items():
                ippool_allocation_list.append(
                    {
                        "name": ippool["name"],
                        "range": ippool["spec"]["range"],
                        "allocation_number": allocation_number,
                        "allocation_data": allocation_data,
                    }
                )

        return ippool_allocation_list

    @staticmethod
    def _remove_duplicate_list_items(list_to_remove_duplicates: List[Dict]) -> List[Dict]:
        """
        Remove duplicate items from list of dictionaries.

        Args:
            list_to_remove_duplicates: List that may contain duplicates

        Returns:
            List without duplicates
        """
        list_without_duplicates = []
        for list_item in list_to_remove_duplicates:
            if list_item not in list_without_duplicates:
                list_without_duplicates.append(list_item)

        return list_without_duplicates


class WhereaboutsDuplicateIPAddresses(WhereaboutsBaseRule):
    """
    Validate that there are no duplicate Whereabouts IP addresses.

    Checks if multiple pods have been assigned the same IP address by Whereabouts IPAM,
    which would cause network connectivity issues.
    """

    unique_name = "whereabouts_duplicate_ip_addresses"
    title = "Validate that there are no duplicate whereabouts IP addresses"

    def run_rule(self):
        """
        Check for duplicate IP addresses in Whereabouts allocations.

        Returns:
            RuleResult indicating if duplicate IPs were found
        """
        pod_whereabouts_ip_list = self.get_pod_whereabouts_ip_list()

        # Collect all active IPs
        active_ip_list = []
        for pod in pod_whereabouts_ip_list:
            active_ip_list.extend(pod["ips"])

        # Find duplicates
        duplicate_ip_list = [ip for i, ip in enumerate(active_ip_list) if ip in active_ip_list[:i]]

        if not duplicate_ip_list:
            return RuleResult.passed()

        # Build list of pods with duplicate IPs
        temp_duplicate_ip_pod_list = []
        for duplicate_ip in duplicate_ip_list:
            for pod in pod_whereabouts_ip_list:
                if duplicate_ip in pod["ips"]:
                    temp_duplicate_ip_pod_list.append(
                        {"name": pod["name"], "namespace": pod["namespace"], "ip": duplicate_ip}
                    )

        duplicate_ip_pod_list = self._remove_duplicate_list_items(temp_duplicate_ip_pod_list)

        # Build failure message
        results = []
        for pod in duplicate_ip_pod_list:
            results.append(f"--> Pod {pod['namespace']}/{pod['name']} has a duplicate IP {pod['ip']}")

        message = f"Duplicate whereabouts IP addresses have been detected:\n{chr(10).join(results)}"
        return RuleResult.failed(message)


class WhereaboutsMissingPodrefs(WhereaboutsBaseRule):
    """
    Validate that there are no missing whereabouts podrefs in ippool allocations.

    Checks if IPPool allocations have missing or invalid pod references,
    which can indicate stale allocations or IPAM database corruption.
    """

    unique_name = "whereabouts_missing_podrefs"
    title = "Validate that there are no missing whereabouts podrefs in ippool allocations"

    def get_missing_podref_ip_list(self) -> List:
        """
        Get list of IPs with missing pod references from IPPool allocations.

        Returns:
            List of IP addresses that have allocations without pod references
        """
        ippool_allocation_list = self.get_ippool_allocation_list()

        # Find allocations without podref
        missing_podref_allocation_list = []
        for allocation in ippool_allocation_list:
            if "podref" not in allocation["allocation_data"]:
                missing_podref_allocation_list.append(allocation)

        # Convert allocation numbers to IPs
        missing_podref_ip_list = []
        for allocation in missing_podref_allocation_list:
            network = ipaddress.ip_network(allocation["range"], strict=False)
            ip_address = network[0] + int(allocation["allocation_number"])
            missing_podref_ip_list.append(ip_address)

        return missing_podref_ip_list

    def run_rule(self):
        """
        Check for missing pod references in IPPool allocations.

        Returns:
            RuleResult indicating if missing podrefs were found
        """

        # Get IPs with missing podrefs
        missing_podref_ip_list = self.get_missing_podref_ip_list()

        if not missing_podref_ip_list:
            return RuleResult.passed()

        # Check if these IPs are assigned to active pods
        pod_whereabouts_ip_list = self.get_pod_whereabouts_ip_list()
        results = []

        for ip_missing_podref in missing_podref_ip_list:
            for pod in pod_whereabouts_ip_list:
                for pod_ip in pod["ips"]:
                    if ip_missing_podref == ipaddress.ip_address(pod_ip):
                        results.append(
                            f"--> Pod {pod['namespace']}/{pod['name']} " f"has a missing podref for IP {pod_ip}"
                        )

        if not results:
            # Missing podrefs but no active pods using them - still a problem (stale allocations)
            return RuleResult.failed(
                f"Found {len(missing_podref_ip_list)} IPPool allocations " f"without pod references (stale allocations)"
            )

        message = f"Missing whereabouts podrefs in ippool allocations have been detected:\n{chr(10).join(results)}"
        return RuleResult.failed(message)


class WhereaboutsMissingAllocations(WhereaboutsBaseRule):
    """
    Validate that there are no missing whereabouts ippool allocations.

    Checks if active pods have IP addresses that are not recorded in IPPool allocations,
    which indicates IPAM database inconsistency.
    """

    unique_name = "whereabouts_missing_allocations"
    title = "Validate that there are no missing whereabouts ippool allocations"

    def get_allocated_ip_list(self) -> List:
        """
        Get list of all allocated IPs from IPPool configurations.

        Returns:
            List of IP addresses that have allocations in IPPools
        """
        ippool_configs = self.gather_ippool_configs()
        allocated_ip_list = []

        for ippool in ippool_configs:
            network = ipaddress.ip_network(ippool["spec"]["range"], strict=False)
            for allocation in ippool["spec"]["allocations"]:
                allocated_ip_list.append(network[0] + int(allocation))

        return allocated_ip_list

    def get_missing_ip_allocation_pod_list(self, allocated_ip_list: List) -> List[Dict]:
        """
        Get list of pods with IPs that lack corresponding IPPool allocations.

        Args:
            allocated_ip_list: List of IPs that have allocations in IPPools

        Returns:
            List of pods with IPs that are not in the allocated_ip_list
        """
        # Get pods with Whereabouts IPs
        temp_missing_ip_allocation_pod_list = copy.deepcopy(self.get_pod_whereabouts_ip_list())

        # Remove IPs that have allocations
        for ippool_ip in allocated_ip_list:
            for pod in temp_missing_ip_allocation_pod_list:
                for pod_ip in pod["ips"][:]:  # Create a copy of list for iteration
                    if ipaddress.ip_address(pod_ip) == ippool_ip:
                        pod["ips"].remove(pod_ip)

        # Filter to pods that still have IPs without allocations
        missing_ip_allocation_pod_list = [pod for pod in temp_missing_ip_allocation_pod_list if pod["ips"]]

        return missing_ip_allocation_pod_list

    def run_rule(self):
        """
        Check for pods with IPs that lack corresponding IPPool allocations.

        Returns:
            RuleResult indicating if missing allocations were found
        """
        # Get all allocated IPs from IPPools
        allocated_ip_list = self.get_allocated_ip_list()

        # Get pods with IPs that lack allocations
        missing_ip_allocation_pod_list = self.get_missing_ip_allocation_pod_list(allocated_ip_list)

        if not missing_ip_allocation_pod_list:
            return RuleResult.passed()

        # Build failure message
        results = []
        for pod in missing_ip_allocation_pod_list:
            for pod_ip in pod["ips"]:
                results.append(
                    f"--> Pod {pod['namespace']}/{pod['name']} "
                    f"has a missing IP allocation for IP {json.dumps(pod_ip).strip('\"')}"
                )

        message = f"Missing whereabouts ippool allocations have been detected:\n{chr(10).join(results)}"
        return RuleResult.failed(message)


class WhereaboutsExistingAllocations(WhereaboutsBaseRule):
    """
    Validate that all whereabouts ippool allocations match their corresponding pod and pod IP.

    Checks if IPPool allocations have correct pod references that match the actual
    pods using those IP addresses.
    """

    unique_name = "whereabouts_existing_allocations"
    title = "Validate that all whereabouts ippool allocations match their corresponding pod and pod IP"

    def run_rule(self):
        """
        Verify existing IP allocations match their pod references.

        Returns:
            RuleResult indicating if mismatched allocations were found
        """
        pod_whereabouts_ip_list = self.get_pod_whereabouts_ip_list()
        ippool_allocation_list = self.get_ippool_allocation_list()

        # Start with all allocations as "incorrect" and remove the ones that match
        incorrect_ippool_allocation_list = copy.deepcopy(ippool_allocation_list)

        for pod in pod_whereabouts_ip_list:
            for ip in pod["ips"]:
                pod_ip = ipaddress.ip_address(ip)

                for allocation in incorrect_ippool_allocation_list[:]:  # Iterate over copy
                    network = ipaddress.ip_network(allocation["range"], strict=False)
                    allocation_ip = network[0] + int(allocation["allocation_number"])

                    if pod_ip == allocation_ip:
                        # Check if podref matches
                        if "podref" in allocation["allocation_data"]:
                            podref = json.dumps(allocation["allocation_data"]["podref"]).replace('"', "").split("/")
                            if len(podref) == 2 and podref[0] == pod["namespace"] and podref[1] == pod["name"]:
                                # This allocation is correct, remove from incorrect list
                                incorrect_ippool_allocation_list.remove(allocation)

        if not incorrect_ippool_allocation_list:
            return RuleResult.passed()

        # Build failure message for allocations that don't match
        results = []
        for allocation in incorrect_ippool_allocation_list:
            if "podref" in allocation["allocation_data"]:
                results.append(
                    f"--> Allocation in ippool {allocation['name']} with allocation number "
                    f"{allocation['allocation_number']} does not match the pod listed in its podref: "
                    f"{allocation['allocation_data']['podref']}"
                )

        if not results:
            return RuleResult.passed()

        message = (
            "There is a problem with the following ippool allocations. "
            "These allocations do not match their corresponding pod name and pod IP "
            f"based on the allocation podrefs:\n{chr(10).join(results)}"
        )
        return RuleResult.failed(message)
