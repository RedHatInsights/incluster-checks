"""
Kubernetes/OpenShift validations ported from HealthChecks.

Direct port from: HealthChecks/flows/K8s/k8s_components/k8s_sanity_checks.py
"""

import json

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives, Status


class AllPodsReadyAndRunning(OrchestratorRule):
    """Verify all pods are ready and in running state across all namespaces."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_pods_are_running_all_namespaces"
    title = "Verify all pods are ready and on running state"

    def run_rule(self):
        """Check if all pods across all namespaces are ready and running."""
        ready_pods, not_running_pods = self._get_pods_lists()

        if len(ready_pods) == 0:
            return RuleResult.failed("Did not get any pods from 'oc get pods --all-namespaces'")

        if not_running_pods:
            message = "Not all pods are running\n"
            message += "Following pods are not running or partially not ready:\n"

            # Format not-ready pods with details
            for pod_info in not_running_pods:
                namespace = pod_info["namespace"]
                pod_name = pod_info["name"]
                status = pod_info["status"]
                ready = pod_info["ready"]
                message += f"  {namespace}/{pod_name} - Ready: {ready}, Status: {status}\n"

            return RuleResult.failed(message)

        return RuleResult.passed()

    def _get_pods_lists(self):
        """
        Get lists of ready and not-ready pods.

        Returns:
            tuple: (ready_pods_list, not_running_pods_list)
                   Each list contains dicts with pod information
        """
        ready_pods = []
        not_running_pods = []

        # Use helper method from OrchestratorRule (logs command automatically)
        pod_objects = self.get_all_pods(all_namespaces=True, timeout=45)

        if not pod_objects:
            return [], []

        for pod in pod_objects:
            pod_data = pod.as_dict()
            namespace = pod_data["metadata"]["namespace"]
            pod_name = pod_data["metadata"]["name"]
            status_dict = pod_data.get("status", {})

            # Get phase (Running, Pending, Failed, etc.)
            phase = status_dict.get("phase", "Unknown")

            # Skip Completed jobs
            if phase == "Succeeded":
                continue

            # Get container statuses
            container_statuses = status_dict.get("containerStatuses", [])

            # Calculate ready containers
            total_containers = len(container_statuses)
            ready_containers = sum(1 for c in container_statuses if c.get("ready", False))
            ready_str = f"{ready_containers}/{total_containers}"

            pod_info = {
                "namespace": namespace,
                "name": pod_name,
                "status": phase,
                "ready": ready_str,
            }

            # Check if pod is not running or not all containers are ready
            if phase != "Running":
                not_running_pods.append(pod_info)
            elif ready_containers != total_containers:
                not_running_pods.append(pod_info)
            else:
                ready_pods.append(pod_info)

        return ready_pods, not_running_pods


class NodesAreReady(OrchestratorRule):
    """Verify all nodes are in Ready state."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_nodes_are_ready"
    title = "Verify nodes are ready"

    def run_rule(self):
        """Check if all nodes are in Ready state."""
        ready_list, not_ready_list, warned_list = self._get_nodes_lists()

        if len(ready_list) == 0:
            return RuleResult.failed("Did not get nodes list from 'oc get nodes'")

        error_messages = []

        if not_ready_list:
            error_messages.append("The following nodes are not ready:\n  " + "\n  ".join(not_ready_list))

        if warned_list:
            error_messages.append(
                "The following nodes are ready but having some issues:\n  " + "\n  ".join(warned_list)
            )

        if error_messages:
            return RuleResult.failed("\n\n".join(error_messages))

        return RuleResult.passed()

    def _get_nodes_lists(self):
        """
        Get lists of ready, not-ready, and warned nodes.

        Returns:
            tuple: (ready_list, not_ready_list, warned_list)
                   - ready_list: node names in Ready state
                   - not_ready_list: node names not in Ready state
                   - warned_list: "node_name - status" for nodes with warnings
        """
        ready_list = []
        not_ready_list = []
        warned_list = []

        # Get all nodes
        node_objects = self.get_all_nodes(timeout=45)

        if not node_objects:
            return [], [], []

        for node in node_objects:
            node_data = node.as_dict()
            node_name = node_data["metadata"]["name"]
            status_dict = node_data.get("status", {})
            conditions = status_dict.get("conditions", [])

            # Find Ready condition
            ready_condition = None
            for condition in conditions:
                if condition.get("type") == "Ready":
                    ready_condition = condition
                    break

            if not ready_condition:
                not_ready_list.append(node_name)
                continue

            ready_status = ready_condition.get("status", "Unknown")

            if ready_status == "True":
                # Check for other warning conditions (DiskPressure, MemoryPressure, etc.)
                warning_conditions = []
                for condition in conditions:
                    condition_type = condition.get("type")
                    condition_status = condition.get("status", "False")
                    if (
                        condition_type != "Ready"
                        and condition_status == "True"
                        and condition_type in ["DiskPressure", "MemoryPressure", "PIDPressure", "NetworkUnavailable"]
                    ):
                        warning_conditions.append(condition_type)

                if warning_conditions:
                    warned_list.append(f"{node_name} - Ready,{','.join(warning_conditions)}")
                else:
                    ready_list.append(node_name)
            else:
                not_ready_list.append(node_name)

        return ready_list, not_ready_list, warned_list


class NodesCpuAndMemoryStatus(OrchestratorRule):
    """Check node CPU and memory usage against thresholds."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "check_nodes_cpu_and_memory"
    title = "Check nodes CPU and memory"

    THRESHOLD_ERROR = 80
    THRESHOLD_CRITICAL = 90

    def run_rule(self):
        """Check CPU and memory usage for all nodes."""
        try:
            _, nodes_info, _ = self.run_oc_command("adm", ["top", "nodes", "--no-headers"], timeout=45)
        except UnExpectedSystemOutput:
            return RuleResult.failed("Failed to get nodes CPU and memory information")

        if not nodes_info or not nodes_info.strip():
            return RuleResult.failed("No node metrics available from 'oc adm top nodes'")

        nodes_with_high_cpu = []
        nodes_with_high_memory = []
        is_critical = False

        for line in nodes_info.strip().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue

            node_name = parts[0]
            cpu_percent_str = parts[2]  # e.g., "50%"
            memory_percent_str = parts[4]  # e.g., "50%"

            # Parse CPU percentage
            if not cpu_percent_str.endswith("%"):
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd="oc adm top nodes --no-headers",
                    output=line,
                    message=f"Expected CPU percentage with % sign, got: {cpu_percent_str}",
                )

            try:
                cpu_percent = int(cpu_percent_str.rstrip("%"))
            except ValueError:
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd="oc adm top nodes --no-headers",
                    output=line,
                    message=f"Could not parse CPU percentage: {cpu_percent_str}",
                )

            # Parse memory percentage
            if not memory_percent_str.endswith("%"):
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd="oc adm top nodes --no-headers",
                    output=line,
                    message=f"Expected memory percentage with % sign, got: {memory_percent_str}",
                )

            try:
                memory_percent = int(memory_percent_str.rstrip("%"))
            except ValueError:
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd="oc adm top nodes --no-headers",
                    output=line,
                    message=f"Could not parse memory percentage: {memory_percent_str}",
                )

            # Check thresholds
            if cpu_percent > self.THRESHOLD_ERROR:
                nodes_with_high_cpu.append(f"{node_name} ({cpu_percent}%)")
                if cpu_percent > self.THRESHOLD_CRITICAL:
                    is_critical = True

            if memory_percent > self.THRESHOLD_ERROR:
                nodes_with_high_memory.append(f"{node_name} ({memory_percent}%)")
                if memory_percent > self.THRESHOLD_CRITICAL:
                    is_critical = True

        if not nodes_with_high_cpu and not nodes_with_high_memory:
            return RuleResult.passed()

        error_messages = []
        if nodes_with_high_cpu:
            error_messages.append(
                f"The following nodes have high CPU usage (>{self.THRESHOLD_ERROR}%):\n  "
                + "\n  ".join(nodes_with_high_cpu)
            )

        if nodes_with_high_memory:
            error_messages.append(
                f"The following nodes have high memory usage (>{self.THRESHOLD_ERROR}%):\n  "
                + "\n  ".join(nodes_with_high_memory)
            )

        error_messages.append(f"\nNodes CPU and memory usage:\n{nodes_info}")

        message = "\n\n".join(error_messages)

        if is_critical:
            return RuleResult.failed(
                message + f"\n\nCRITICAL: At least one node exceeds {self.THRESHOLD_CRITICAL}% threshold"
            )

        return RuleResult.failed(message)


class ValidateNamespaceStatus(OrchestratorRule):
    """Validate all namespaces are in Active status."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_namespaces_are_in_active_status"
    title = "Validate namespace in Active status"

    def run_rule(self):
        """Check if all namespaces are in Active status."""
        namespace_objects = self.get_all_namespaces(timeout=45)

        if not namespace_objects:
            return RuleResult.failed("No namespaces found in cluster")

        inactive_namespaces = []

        for ns in namespace_objects:
            ns_data = ns.as_dict()
            ns_name = ns_data["metadata"]["name"]
            status_dict = ns_data.get("status", {})
            phase = status_dict.get("phase", "Unknown")

            if phase != "Active":
                inactive_namespaces.append(f"{ns_name} - {phase}")

        if inactive_namespaces:
            message = "Below namespaces are not in Active state:\n  "
            message += "\n  ".join(inactive_namespaces)
            return RuleResult.warning(message)

        return RuleResult.passed()


class ValidateAllDaemonsetsScheduled(OrchestratorRule):
    """Validate all daemonsets have the desired number of available copies."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_basic_daemonset_scheduled"
    title = "Validate all daemonsets are properly scheduled"

    def run_rule(self):
        """Check if all daemonsets have desired number of available copies."""
        try:
            _, out, _ = self.run_oc_command("get", ["daemonsets", "--all-namespaces", "-o", "json"], timeout=45)
        except UnExpectedSystemOutput:
            return RuleResult.failed("Failed to get daemonsets")

        try:
            daemonsets_data = json.loads(out)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="oc get daemonsets --all-namespaces -o json",
                output=out,
                message=f"Failed to parse JSON: {e}",
            )

        problematic_daemonsets = []

        for item in daemonsets_data.get("items", []):
            metadata = item.get("metadata", {})
            name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = item.get("status", {})

            desired_num = int(status.get("desiredNumberScheduled", 0))
            current_num = int(status.get("currentNumberScheduled", 0))
            number_unavailable = int(status.get("numberUnavailable", 0))

            # Skip daemonsets with no desired pods (no matching nodes)
            if desired_num == 0:
                continue

            # Check if pods are being scheduled (most critical issue)
            if current_num < desired_num:
                problematic_daemonsets.append(
                    f"{namespace}/{name} - Desired: {desired_num}, Current: {current_num} "
                    f"(pods not being scheduled on all nodes)"
                )
            # Only flag as problematic if there are pods explicitly marked as unavailable
            # This indicates a real issue rather than just initialization delay
            elif number_unavailable > 0:
                problematic_daemonsets.append(f"{namespace}/{name} - {number_unavailable} pod(s) unavailable")

        if problematic_daemonsets:
            message = "Following daemonsets have scheduling or availability issues:\n  "
            message += "\n  ".join(problematic_daemonsets)
            return RuleResult.failed(message)

        return RuleResult.passed()


class AllDeploymentsAvailable(OrchestratorRule):
    """Validate all deployments are available and ready."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_deployments_available"
    title = "Verify all deployments are available"

    def run_rule(self):
        """Check if all deployments have Available condition set to True."""
        deployment_objects = self.get_all_deployments()

        if not deployment_objects:
            return RuleResult.failed("No deployments found in cluster")

        unavailable_deployments = []

        for item in deployment_objects:
            item_data = item.as_dict()
            metadata = item_data.get("metadata", {})
            name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = item_data.get("status", {})
            conditions = status.get("conditions", [])

            # Check for "Available" condition
            available_condition = None
            for condition in conditions:
                if condition.get("type") == "Available":
                    available_condition = condition
                    break

            # If no Available condition found or it's not True, deployment is unavailable
            if not available_condition:
                unavailable_deployments.append(f"{namespace}/{name} - No Available condition found")
            elif available_condition.get("status") != "True":
                reason = available_condition.get("reason", "Unknown")
                message = available_condition.get("message", "No message")
                unavailable_deployments.append(
                    f"{namespace}/{name} - Status: {available_condition.get('status')}, "
                    f"Reason: {reason}, Message: {message}"
                )

        if unavailable_deployments:
            message = "Following deployments are not available:\n  "
            message += "\n  ".join(unavailable_deployments)
            return RuleResult.failed(message)

        return RuleResult.passed()


class CheckDeploymentsReplicaStatus(OrchestratorRule):
    """Validate all deployments have correct replica counts."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "check_deployments_replica_status"
    title = "Verify deployment replica counts"

    def run_rule(self):
        """Check if all deployments have desired number of replicas ready."""
        deployment_objects = self.get_all_deployments()

        if not deployment_objects:
            return RuleResult.failed("No deployments found in cluster")

        problematic_deployments = []

        for item in deployment_objects:
            item_data = item.as_dict()
            metadata = item_data.get("metadata", {})
            name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            spec = item_data.get("spec", {})
            status = item_data.get("status", {})

            # Get replica counts
            desired_replicas = int(spec.get("replicas", 0))
            ready_replicas = int(status.get("readyReplicas", 0))
            available_replicas = int(status.get("availableReplicas", 0))
            updated_replicas = int(status.get("updatedReplicas", 0))

            # Check if ready replicas match desired
            if ready_replicas != desired_replicas:
                problematic_deployments.append(
                    f"{namespace}/{name} - Desired: {desired_replicas}, Ready: {ready_replicas}"
                )
            # Check if available replicas match desired
            elif available_replicas != desired_replicas:
                problematic_deployments.append(
                    f"{namespace}/{name} - Desired: {desired_replicas}, Available: {available_replicas}"
                )
            # Check if updated replicas match desired (rollout not complete)
            elif updated_replicas != desired_replicas:
                problematic_deployments.append(
                    f"{namespace}/{name} - Desired: {desired_replicas}, Updated: {updated_replicas} "
                    "(rollout in progress)"
                )

        if problematic_deployments:
            message = "Following deployments have replica count issues:\n  "
            message += "\n  ".join(problematic_deployments)
            return RuleResult.failed(message)

        return RuleResult.passed()


# Checking statefulsets is important as they are used for critical components like alerts and monitoring.
class AllStatefulsetsReady(OrchestratorRule):
    """Validate all statefulsets are in Ready state."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "all_statefulsets_ready"
    title = "Verify all statefulsets are ready"

    def run_rule(self):
        """Check if all statefulsets have ready replicas matching desired replicas."""
        # Get all statefulsets from all namespaces
        statefulset_objects = self.get_all_statefulsets()

        if not statefulset_objects:
            return RuleResult.warning("No statefulsets found in cluster")

        not_ready_statefulsets = []

        for item in statefulset_objects:
            item_data = item.as_dict()
            metadata = item_data.get("metadata", {})
            name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            spec = item_data.get("spec", {})
            status = item_data.get("status", {})

            desired_replicas = int(spec.get("replicas", 0))
            ready_replicas = int(status.get("readyReplicas", 0))
            # Only check statefulsets that are expected to have replicas (skip those with 0 desired replicas)
            if ready_replicas != desired_replicas:
                not_ready_statefulsets.append(
                    f"{namespace}/{name} - Desired: {desired_replicas}, Ready: {ready_replicas}"
                )
        # Check if there are any statefulsets that are not ready
        if not_ready_statefulsets:
            message = "Following statefulsets are not ready:\n  "
            message += "\n  ".join(not_ready_statefulsets)
            return RuleResult.failed(message)

        return RuleResult.passed()


class OpenshiftOperatorStatus(OrchestratorRule):
    """Check OpenShift cluster operators status and display their status information."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "check_openshift_operators_status"
    title = "Operators Status"

    def run_rule(self):
        """
        Check cluster operators status via oc get clusteroperators.

        Returns:
            RuleResult with info() if all operators are available and not progressing,
            or failed() if any operators are unavailable or progressing.
        """
        unavailable_operators = []
        progressing_operators = []
        table_data = []
        headers = ["Name", "Version", "Available", "Progressing", "Degraded", "Since", "Message"]

        try:
            _, operators_output, _ = self.run_oc_command(
                "get", ["clusteroperators.config.openshift.io", "--no-headers"], timeout=45
            )
        except UnExpectedSystemOutput:
            return RuleResult.failed("Failed to get cluster operators status")

        if not operators_output or not operators_output.strip():
            return RuleResult.failed("No cluster operators found")

        for operator_line in operators_output.strip().splitlines():
            operator_values = operator_line.split()
            operator_row = []

            for i in range(len(headers)):
                try:
                    value = operator_values[i]
                    # Check for unavailable operators (Available=False)
                    if i == 2 and value == "False":
                        unavailable_operators.append(operator_values[0])
                    # Check for progressing operators (Progressing=True)
                    if i == 3 and value == "True":
                        progressing_operators.append(operator_values[0])
                    operator_row.append(value)
                except IndexError:
                    operator_row.append(" ")

            table_data.append(operator_row)

        # Sort table: Available=False first, then Progressing=True
        # This puts problematic operators at the top
        table_data = sorted(table_data, key=lambda x: (x[2] == "True", x[3] == "False"))

        # Build failure message if there are issues
        if unavailable_operators or progressing_operators:
            error_messages = []
            if unavailable_operators:
                error_messages.append(
                    "The following operators are not available:\n  " + "\n  ".join(unavailable_operators)
                )
            if progressing_operators:
                error_messages.append(
                    "The following operators are in progress:\n  " + "\n  ".join(progressing_operators)
                )

            # Return with dedicated table fields
            return RuleResult(
                status=Status.FAILED,
                message="\n\n".join(error_messages),
                table_headers=headers,
                table_data=table_data,
            )

        # Return INFO status with table
        return RuleResult(
            status=Status.INFO,
            message="All operators are available and stable",
            table_headers=headers,
            table_data=table_data,
        )


# Rule to validate all policies are compliant
class ValidateAllPoliciesCompliant(OrchestratorRule):
    """Validate all Open Cluster Management policies are compliant."""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "validate_all_policies_compliant"
    title = "Verify all policies are in compliant state"

    def run_rule(self):
        """Check if all OCM policies are in Compliant state"""
        try:
            # Run the oc command to get all policies from all namespaces
            _, policies_output, _ = self.run_oc_command(
                "get", ["policies.policy.open-cluster-management.io", "--all-namespaces", "-o", "json"], timeout=45
            )
        except UnExpectedSystemOutput:
            return RuleResult.failed("Failed to get policies from cluster")

        try:
            policies_data = json.loads(policies_output)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="oc get policies.policy.open-cluster-management.io --all-namespaces -o json",
                output=policies_output,
                message=f"Failed to parse JSON: {e}",
            )

        items = policies_data.get("items", [])
        # Check if there are any policies
        if not items:
            return RuleResult.warning("No policies found in cluster")

        non_compliant_policies = []

        for policy in items:
            metadata = policy.get("metadata", {})
            name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = policy.get("status", {})
            compliance_state = status.get("compliant", "Unknown")
            if compliance_state != "Compliant":
                non_compliant_policies.append(f"{namespace}/{name} - {compliance_state}")

        if non_compliant_policies:
            message = f"There are {len(non_compliant_policies)} non-compliant policies:\n  "
            message += "\n  ".join(non_compliant_policies)
            return RuleResult.failed(message)

        return RuleResult.passed()


# Rule to verify OpenShift internal image registry is configured and available
class VerifyInternalRegistry(OrchestratorRule):
    """Verify OpenShift internal image registry is configured and available"""

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_internal_registry"
    title = "Verify internal image registry is configured and available"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if image registry management state is configured.

        Returns:
            PrerequisiteResult indicating if registry should be validated
        """
        try:
            _, registry_config_output, _ = self.run_oc_command(
                "get",
                ["config.imageregistry.operator.openshift.io", "cluster", "-o", "json"],
                timeout=45,
            )
        except UnExpectedSystemOutput:
            return PrerequisiteResult.not_met("Failed to get image registry configuration")

        try:
            registry_config = json.loads(registry_config_output)
        except json.JSONDecodeError as e:
            return PrerequisiteResult.not_met(f"Failed to parse image registry configuration: {e}")

        spec = registry_config.get("spec", {})
        management_state = spec.get("managementState", "Unknown")

        if management_state != "Managed":
            return PrerequisiteResult.not_met(f"Image registry management state is '{management_state}', not 'Managed'")

        return PrerequisiteResult.met()

    def run_rule(self):
        """
        Check if OpenShift internal image registry is properly configured and running.

        """
        # Only check pods if management state is Managed (verified by prerequisite)
        pod_objects = self.get_all_pods(namespace="openshift-image-registry")
        # Check if there are any pods
        if not pod_objects:
            return RuleResult.failed(
                "Image registry is Managed but no registry pods found in openshift-image-registry namespace.\n"
            )

        # Check pod readiness
        not_ready_pods = []

        for pod in pod_objects:
            pod_status = self.get_pod_status(pod)
            if pod_status is None:
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        if not_ready_pods:
            message = "Image registry is Managed but following pods are not ready:\n  "
            message += "\n  ".join(not_ready_pods)
            return RuleResult.failed(message)

        return RuleResult.passed()
