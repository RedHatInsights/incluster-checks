"""
Kubernetes/OpenShift validations ported from HealthChecks.

Direct port from: HealthChecks/flows/K8s/k8s_components/k8s_sanity_checks.py
"""

from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_json


class SubscriptionOperatorRule(OrchestratorRule):
    """Base class for operator health validation rules that check OLM subscriptions.

    Subclasses must define:
        operator_subscription_name (str): The operator package name in the Subscription (e.g., "nfd")
        operator_display_name (str): Human-readable operator name for error messages (e.g., "Node Feature Discovery")
    """

    operator_subscription_name: str = NotImplemented
    operator_display_name: str = NotImplemented

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """Check that the operator has been installed via a Subscription.

        Queries the cluster for a Subscription resource with the
        operator_subscription_name package.  If none is found the rule is not applicable.
        """
        subscriptions_data = self.oc_api.get_operator_subscriptions()

        for sub in subscriptions_data.get("items", []):
            spec = sub.get("spec", {})
            if spec.get("name") == self.operator_subscription_name:
                return PrerequisiteResult.met()

        return PrerequisiteResult.not_met(
            f"{self.operator_subscription_name} operator subscription not found - "
            f"{self.operator_display_name} operator is not installed on this cluster"
        )

    def _check_pod_security_context(self, pod_name: str, security_context: dict[str, object] | None) -> list[str]:
        """Validate pod-level security context has runAsNonRoot set to true.

        Args:
            pod_name: Pod name.
            security_context: Pod-level security context.

        Returns:
            List of validation error messages.
        """
        errors = []
        if security_context is None:
            errors.append(f"Pod {pod_name} has nil SecurityContext")
        elif security_context.get("runAsNonRoot") is None:
            errors.append(f"Pod {pod_name} has nil runAsNonRoot")
        elif not security_context.get("runAsNonRoot"):
            errors.append(
                f"Incorrect runAsNonRoot for pod {pod_name}. "
                f"Expected true, found: {security_context.get('runAsNonRoot')}"
            )
        return errors

    def _check_containers_non_root(self, pod_name: str, all_containers: list[dict[str, object]]) -> list[str]:
        """Validate no container runs as root (runAsUser != 0).

        Args:
            pod_name: Pod name.
            all_containers: Combined containers and initContainers list.

        Returns:
            List of validation error messages.
        """
        errors = []
        if not all_containers:
            errors.append(f"Pod {pod_name} has no containers")
            return errors
        for container in all_containers:
            container_name = container.get("name", "unknown")
            container_sc = container.get("securityContext")
            if container_sc is not None:
                run_as_user = container_sc.get("runAsUser")
                if run_as_user is not None:
                    if not isinstance(run_as_user, int) or isinstance(run_as_user, bool) or run_as_user < 0:
                        errors.append(
                            f"Container '{container_name}' in pod {pod_name} has invalid runAsUser: {run_as_user}"
                        )
                    elif run_as_user == 0:
                        errors.append(f"Container '{container_name}' in pod {pod_name} runs as root (runAsUser=0)")
        return errors

    def validate_namespace_pods_health(self, namespace: str) -> list[str]:
        """Validate all pods in a namespace are Running and Ready.

        Args:
            namespace: Kubernetes namespace to check

        Returns:
            List of error messages. Empty list if all pods are healthy.
        """
        pod_objects = self.oc_api.get_all_pods(namespace=namespace)

        if not pod_objects:
            return [
                f"No pods found in {namespace} namespace. "
                f"{self.operator_display_name} operator may not be fully deployed."
            ]

        not_ready_pods = []
        succeeded_state_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                succeeded_state_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        parts = []
        if succeeded_state_pods:
            parts.append(
                f"{self.operator_display_name} operator has pods in unexpected succeeded state:\n  "
                + "\n  ".join(succeeded_state_pods)
            )
        if not_ready_pods:
            parts.append(
                f"{self.operator_display_name} operator has unhealthy pods in {namespace} namespace:\n  "
                + "\n  ".join(not_ready_pods)
            )

        return parts


class VerifyNfdOperatorHealth(SubscriptionOperatorRule):
    """Verify Node Feature Discovery (NFD) operator pods are healthy.

    NFD sets the stage for cluster functionality by labelling nodes with
    hardware capabilities.  This rule checks that the NFD operator has been
    installed (Subscription exists) and that every pod in the openshift-nfd
    namespace is Running with all containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_nfd_operator_health"
    title = "Verify NFD operator pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482793",
        "https://docs.openshift.com/container-platform/4.18/hardware_enablement"
        "/psap-node-feature-discovery-operator.html",
    ]

    operator_subscription_name = "nfd"
    operator_display_name = "Node Feature Discovery"

    NFD_NAMESPACE = "openshift-nfd"

    def run_rule(self):
        """Verify all pods in the openshift-nfd namespace are Running and Ready."""
        pod_objects = self.oc_api.get_all_pods(namespace=self.NFD_NAMESPACE)

        if not pod_objects:
            return RuleResult.failed(
                f"No pods found in {self.NFD_NAMESPACE} namespace. NFD operator may not be fully deployed."
            )

        not_ready_pods = []
        unknown_status_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                unknown_status_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        if unknown_status_pods:
            return RuleResult.failed("Failed to evaluate status for NFD pod(s):\n  " + "\n  ".join(unknown_status_pods))

        if not_ready_pods:
            message = f"NFD operator has unhealthy pods in {self.NFD_NAMESPACE} namespace:\n  "
            message += "\n  ".join(not_ready_pods)
            return RuleResult.failed(message)

        return RuleResult.passed()


class VerifyNfdPodRestartCount(SubscriptionOperatorRule):
    """Verify NFD pods have zero restart count across all containers.

    A non-zero restart count indicates pod instability caused by crashes,
    OOMKills, or configuration errors, compromising reliable node feature
    labelling.  This rule checks that the NFD operator is installed and
    that every container in the openshift-nfd namespace has restartCount 0.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_nfd_pod_restart_count"
    title = "Verify NFD pod restart count is zero"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/421603419/Verify+NFD+pod+restart+count",
        "https://docs.openshift.com/container-platform/4.18/hardware_enablement"
        "/psap-node-feature-discovery-operator.html",
    ]

    operator_subscription_name = "nfd"
    operator_display_name = "Node Feature Discovery"

    NFD_NAMESPACE = "openshift-nfd"

    def run_rule(self):
        """Verify all containers in openshift-nfd pods have zero restart count."""
        items = self.oc_api.get_pods(namespace=self.NFD_NAMESPACE)

        if not items:
            return RuleResult.failed(
                f"No pods found in {self.NFD_NAMESPACE} namespace. NFD operator may not be fully deployed."
            )

        pods_with_restarts = []

        for pod in items:
            pod_name = pod.name()
            pod_dict = pod.as_dict()
            container_statuses = pod_dict.get("status", {}).get("containerStatuses", [])
            init_container_statuses = pod_dict.get("status", {}).get("initContainerStatuses", [])

            for container in container_statuses + init_container_statuses:
                restart_count = container.get("restartCount", 0)
                if restart_count > 0:
                    container_name = container.get("name", "unknown")
                    pods_with_restarts.append(f"{pod_name}/{container_name}: restartCount={restart_count}")

        if pods_with_restarts:
            message = f"NFD pods in {self.NFD_NAMESPACE} namespace have non-zero restart counts:\n  "
            message += "\n  ".join(pods_with_restarts)
            return RuleResult.failed(message)

        return RuleResult.passed()


class VerifyAcmOperatorHealth(SubscriptionOperatorRule):
    """Verify Advanced Cluster Management (ACM) operator pods are healthy.

    ACM orchestrates multicluster lifecycle management on the hub cluster.
    This rule checks that the ACM operator has been installed (Subscription
    exists), that the ClusterServiceVersion is in Succeeded phase, and that
    every pod in the open-cluster-management namespace is Running with all
    containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_acm_operator_health"
    title = "Verify ACM operator pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418516286",
        "https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes"
        "/2.12/html/install/installing#installing-while-connected-online",
    ]

    operator_subscription_name = "advanced-cluster-management"
    operator_display_name = "Advanced Cluster Management"

    ACM_NAMESPACE = "open-cluster-management"
    ACM_CSV_PATTERN = "advanced-cluster-management"

    def run_rule(self):
        """Verify ACM CSV is Succeeded and all pods in the namespace are Running and Ready."""
        csv_error = self._verify_csv_status()
        pod_error = self._verify_pods_status()

        errors = [e for e in (csv_error, pod_error) if e]
        if errors:
            return RuleResult.failed("\n\n".join(errors))

        return RuleResult.passed()

    def _verify_csv_status(self) -> str | None:
        """Check that the ACM ClusterServiceVersion is in Succeeded phase.

        Uses status.installedCSV from the operator subscription when available
        to identify the active CSV; falls back to pattern matching.

        Returns:
            Error message string if CSV check fails, None if successful.
        """
        _, csv_output, _ = self.oc_api.run_oc_command(
            "get", ["csv", "-n", self.ACM_NAMESPACE, "-o", "json"], timeout=45
        )
        csv_data = parse_json(
            csv_output,
            f"oc get csv -n {self.ACM_NAMESPACE} -o json",
            self.get_host_ip(),
        )

        installed_csv_name = self._get_installed_csv_name()
        if installed_csv_name:
            acm_csvs = [
                csv for csv in csv_data.get("items", []) if csv.get("metadata", {}).get("name") == installed_csv_name
            ]
        else:
            acm_csvs = [
                csv
                for csv in csv_data.get("items", [])
                if self.ACM_CSV_PATTERN in csv.get("metadata", {}).get("name", "")
            ]

        if not acm_csvs:
            return (
                f"No ClusterServiceVersion matching '{self.ACM_CSV_PATTERN}' "
                f"found in {self.ACM_NAMESPACE} namespace"
            )

        not_succeeded = []
        for csv in acm_csvs:
            name = csv.get("metadata", {}).get("name", "unknown")
            phase = csv.get("status", {}).get("phase", "Unknown")
            if phase != "Succeeded":
                reason = csv.get("status", {}).get("reason", "Unknown")
                message = csv.get("status", {}).get("message", "")
                not_succeeded.append(f"{name} - Phase: {phase}, Reason: {reason}, Message: {message}")

        if not_succeeded:
            return "ACM ClusterServiceVersion is not in Succeeded phase:\n  " + "\n  ".join(not_succeeded)

        return None

    def _get_installed_csv_name(self) -> str | None:
        """Look up status.installedCSV from the ACM operator subscription.

        Returns:
            The installedCSV string if found, None otherwise.
        """
        subscriptions_data = self.oc_api.get_operator_subscriptions()
        for sub in subscriptions_data.get("items", []):
            if sub.get("spec", {}).get("name") == self.operator_subscription_name:
                return sub.get("status", {}).get("installedCSV")
        return None

    def _verify_pods_status(self) -> str | None:
        """Check that all pods in the ACM namespace are Running and Ready.

        Returns:
            Error message string if pod check fails, None if successful.
        """
        pod_objects = self.oc_api.get_all_pods(namespace=self.ACM_NAMESPACE)

        if not pod_objects:
            return f"No pods found in {self.ACM_NAMESPACE} namespace. ACM operator may not be fully deployed."

        not_ready_pods = []
        unknown_status_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                unknown_status_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        if unknown_status_pods or not_ready_pods:
            parts = []
            if unknown_status_pods:
                parts.append("Failed to evaluate status for ACM pod(s):\n  " + "\n  ".join(unknown_status_pods))
            if not_ready_pods:
                parts.append(
                    f"ACM operator has unhealthy pods in {self.ACM_NAMESPACE} namespace:\n  "
                    + "\n  ".join(not_ready_pods)
                )
            return "\n\n".join(parts)

        return None


class VerifyNmoOperatorHealth(SubscriptionOperatorRule):
    """Verify Node Maintenance Operator (NMO) pods are healthy.

    NMO provides declarative node maintenance for OpenShift clusters,
    enabling administrators to cordon and drain nodes safely.  This rule
    checks that the NMO operator has been installed (Subscription exists)
    and that every pod in the openshift-workload-availability namespace
    is Running with all containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_nmo_operator_health"
    title = "Verify NMO operator pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418378",
        "https://docs.redhat.com/en/documentation/workload_availability_for_red_hat_openshift"
        "/24.1/html/remediation_fencing_and_maintenance/node-maintenance-operator",
    ]

    operator_subscription_name = "node-maintenance-operator"
    operator_display_name = "Node Maintenance Operator"

    NMO_NAMESPACE = "openshift-workload-availability"

    def run_rule(self):
        """Verify all pods in the openshift-workload-availability namespace are Running and Ready."""
        pod_objects = self.oc_api.get_all_pods(namespace=self.NMO_NAMESPACE)

        if not pod_objects:
            return RuleResult.failed(
                f"No pods found in {self.NMO_NAMESPACE} namespace. NMO operator may not be fully deployed."
            )

        not_ready_pods = []
        unknown_status_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                unknown_status_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        if unknown_status_pods or not_ready_pods:
            parts = []
            if unknown_status_pods:
                parts.append("Failed to evaluate status for NMO pod(s):\n  " + "\n  ".join(unknown_status_pods))
            if not_ready_pods:
                parts.append(
                    f"NMO operator has unhealthy pods in {self.NMO_NAMESPACE} namespace:\n  "
                    + "\n  ".join(not_ready_pods)
                )
            return RuleResult.failed("\n\n".join(parts))

        return RuleResult.passed()


class VerifyFarOperatorHealth(SubscriptionOperatorRule):
    """Verify Fence Agents Remediation (FAR) operator pods are healthy.

    FAR provides automatic node fencing and recovery for hardware failures.
    This rule checks that the FAR operator has been installed (Subscription
    exists) and that every pod in the openshift-workload-availability namespace
    is Running with all containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_far_operator_health"
    title = "Verify FAR operator pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418450754",
        "https://docs.openshift.com/container-platform/4.18/nodes/nodes/eco-fence-agents-remediation-operator.html",
    ]

    operator_subscription_name = "fence-agents-remediation"
    operator_display_name = "Fence Agents Remediation"

    FAR_NAMESPACE = "openshift-workload-availability"

    def run_rule(self):
        """Verify all pods in the openshift-workload-availability namespace are Running and Ready."""
        pod_objects = self.oc_api.get_all_pods(namespace=self.FAR_NAMESPACE)

        if not pod_objects:
            return RuleResult.failed(
                f"No pods found in {self.FAR_NAMESPACE} namespace. FAR operator may not be fully deployed."
            )

        not_ready_pods = []
        unknown_status_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                unknown_status_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        if unknown_status_pods or not_ready_pods:
            parts = []
            if unknown_status_pods:
                parts.append("Failed to evaluate status for FAR pod(s):\n  " + "\n  ".join(unknown_status_pods))
            if not_ready_pods:
                parts.append(
                    f"FAR operator has unhealthy pods in {self.FAR_NAMESPACE} namespace:\n  "
                    + "\n  ".join(not_ready_pods)
                )
            return RuleResult.failed("\n\n".join(parts))

        return RuleResult.passed()


class VerifyFarContainerNonRoot(SubscriptionOperatorRule):
    """Verify FAR (Fence Agents Remediation) container runs as non-root user.

    Checks that FAR operator pods have proper security context:
    - Pod-level runAsNonRoot is set to true
    - No container runs as root (runAsUser != 0)
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_far_container_non_root"
    title = "Verify FAR container runs as non-root user"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418450775",
        "https://docs.openshift.com/container-platform/4.18/nodes/pods/nodes-pods-configuring.html",
    ]

    operator_subscription_name = "fence-agents-remediation"
    operator_display_name = "Fence Agents Remediation"

    FAR_POD_LABEL_KEY = "app.kubernetes.io/name"
    FAR_POD_LABEL_VALUE = "fence-agents-remediation-operator"

    def run_rule(self):
        """Check if FAR pods run as non-root user with proper security context."""
        pod_objects = self.oc_api.get_pods(labels={self.FAR_POD_LABEL_KEY: self.FAR_POD_LABEL_VALUE})

        if not pod_objects:
            return RuleResult.failed(
                f"No FAR pods found with label {self.FAR_POD_LABEL_KEY}={self.FAR_POD_LABEL_VALUE}"
            )

        error_messages = []

        for pod in pod_objects:
            pod_name = pod.name()
            spec = pod.as_dict().get("spec", {})

            error_messages.extend(self._check_pod_security_context(pod_name, spec.get("securityContext")))

            all_containers = spec.get("containers", []) + spec.get("initContainers", [])
            error_messages.extend(self._check_containers_non_root(pod_name, all_containers))

        if error_messages:
            message = "FAR operator pods doesn't have proper security context:\n"
            for msg in error_messages:
                message += f"- {msg}\n"
            return RuleResult.failed(message)

        return RuleResult.passed()


class VerifyMdrOperatorHealth(SubscriptionOperatorRule):
    """Verify Machine Deletion Remediation (MDR) operator pods are healthy.

    MDR is part of Red Hat Workload Availability (RHWA) and provides automated
    machine deletion remediation for unhealthy nodes. This rule checks that the
    MDR operator has been installed (Subscription exists) and that every pod in
    the openshift-workload-availability namespace is Running with all containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_mdr_operator_health"
    title = "Verify MDR operator pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418399/Verify+MDR+operator+health",
        "https://docs.redhat.com/en/documentation/workload_availability_for_red_hat_openshift"
        "/23.3/html/remediation_fencing_and_maintenance/machine-deletion-remediation-operator-remediate-nodes",
    ]

    operator_subscription_name = "openshift-workload-availability"
    operator_display_name = "Machine Deletion Remediation"

    def run_rule(self):
        """Verify all pods in the openshift-workload-availability namespace are Running and Ready."""
        errors = self.validate_namespace_pods_health(self.operator_subscription_name)
        if errors:
            return RuleResult.failed("\n\n".join(errors))
        return RuleResult.passed()
