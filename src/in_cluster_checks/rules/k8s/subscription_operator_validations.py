"""
Subscription operator validations for OpenShift clusters.

Validates health and status of subscription operators.
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
        """Validate no container runs as root (runAsUser != 0, runAsNonRoot not false).

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
                run_as_non_root = container_sc.get("runAsNonRoot")
                if run_as_non_root is not None and not run_as_non_root:
                    errors.append(f"Container '{container_name}' in pod {pod_name} has runAsNonRoot set to false")
                run_as_user = container_sc.get("runAsUser")
                if run_as_user is not None:
                    if not isinstance(run_as_user, int) or isinstance(run_as_user, bool) or run_as_user < 0:
                        errors.append(
                            f"Container '{container_name}' in pod {pod_name} has invalid runAsUser: {run_as_user}"
                        )
                    elif run_as_user == 0:
                        errors.append(f"Container '{container_name}' in pod {pod_name} runs as root (runAsUser=0)")
        return errors

    def validate_namespace_pods_health(
        self,
        namespace: str,
        allow_succeeded: bool = False,
    ) -> list[str]:
        """Validate all pods in a namespace are Running and Ready.

        Args:
            namespace: Kubernetes namespace to check
            allow_succeeded: If True, skip pods in Succeeded phase (for namespaces with legitimate completed jobs).

        Returns:
            List of error messages. Empty list if all pods are healthy.
        """
        pod_objects = self.oc_api.get_all_pods(namespace=namespace)

        if not pod_objects:
            return [f"No pods found in {namespace} namespace."]

        not_ready_pods = []
        unexpected_succeeded_pods = []

        for pod in pod_objects:
            pod_status = self.oc_api.get_pod_status(pod)
            if pod_status is None:
                if not allow_succeeded:
                    pod_name = pod.as_dict().get("metadata", {}).get("name", "unknown")
                    unexpected_succeeded_pods.append(pod_name)
                continue
            if not pod_status["all_containers_ready"]:
                not_ready_pods.append(pod_status["status_message"])

        parts = []
        if unexpected_succeeded_pods:
            parts.append(
                f"Pods in unexpected succeeded state in {namespace} namespace:\n  "
                + "\n  ".join(unexpected_succeeded_pods)
            )
        if not_ready_pods:
            parts.append(f"Unhealthy pods in {namespace} namespace:\n  " + "\n  ".join(not_ready_pods))

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
        errors = self.validate_namespace_pods_health(self.NFD_NAMESPACE)
        if errors:
            return RuleResult.failed("\n\n".join(errors))
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
        errors = self.validate_namespace_pods_health(self.ACM_NAMESPACE, allow_succeeded=True)
        if errors:
            return "\n\n".join(errors)

        return None


class VerifyWorkloadAvailabilityNamespaceHealth(SubscriptionOperatorRule):
    """Verify all pods in the openshift-workload-availability namespace are healthy.

    The openshift-workload-availability namespace hosts operators for node
    maintenance (NMO), fence-agents remediation (FAR), and machine-deletion
    remediation (MDR).  This rule checks that at least one of those operators
    has been installed (Subscription exists) and that every pod in the
    namespace is Running with all containers ready.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "verify_workload_availability_namespace_health"
    title = "Verify workload availability namespace pods are healthy"
    supported_profiles = {"telco-base"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418378",
        "https://docs.redhat.com/en/documentation/workload_availability_for_red_hat_openshift"
        "/24.1/html/remediation_fencing_and_maintenance/node-maintenance-operator",
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418450754",
        "https://docs.openshift.com/container-platform/4.18/nodes/nodes/eco-fence-agents-remediation-operator.html",
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418399/Verify+MDR+operator+health",
        "https://docs.redhat.com/en/documentation/workload_availability_for_red_hat_openshift"
        "/23.3/html/remediation_fencing_and_maintenance/machine-deletion-remediation-operator-remediate-nodes",
    ]

    WORKLOAD_AVAILABILITY_NAMESPACE = "openshift-workload-availability"
    SUBSCRIPTION_NAMES = [
        "node-maintenance-operator",
        "fence-agents-remediation",
        "machine-deletion-remediation-operator",
    ]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """Check that at least one workload-availability operator is installed."""
        subscriptions_data = self.oc_api.get_operator_subscriptions()

        for sub in subscriptions_data.get("items", []):
            spec = sub.get("spec", {})
            if spec.get("name") in self.SUBSCRIPTION_NAMES:
                return PrerequisiteResult.met()

        return PrerequisiteResult.not_met(
            "No workload availability operator subscription found (NMO, FAR, or MDR) - "
            "none of the workload availability operators are installed on this cluster"
        )

    def run_rule(self):
        """Verify all pods in the openshift-workload-availability namespace are Running and Ready."""
        errors = self.validate_namespace_pods_health(self.WORKLOAD_AVAILABILITY_NAMESPACE)
        if errors:
            return RuleResult.failed("\n\n".join(errors))
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
