"""
SR-IOV Network Operator validations for OpenShift clusters.

Validates that the SR-IOV Network Operator is correctly configured for
NVIDIA Spectrum-X deployments.
"""

from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.rules.k8s.subscription_operator_validations import SubscriptionOperatorRule
from in_cluster_checks.utils.enums import Objectives


class VerifySriovOperatorConfigured(SubscriptionOperatorRule):
    """Verify the SR-IOV Network Operator is installed and correctly configured.

    Checks that the `SriovOperatorConfig` resource has the `manageSoftwareBridges`
    feature gate enabled, that the operator's pods in the
    openshift-sriov-network-operator namespace are Running and Ready, and that
    the operator subscription has the NVIDIA OVS-CNI image override applied
    (required to avoid validation pods getting stuck due to missing ovs-cni
    binaries).

    Reference: https://github.com/sdambo-git/spc-x-host-configuration#configuring-sriov-operator
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_sriov_operator_configured"
    title = "Verify SR-IOV Network Operator is configured correctly"
    supported_profiles = {"spectrum-x"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/505184364",
        "https://github.com/sdambo-git/spc-x-host-configuration#configuring-sriov-operator",
    ]

    operator_subscription_name = "sriov-network-operator"
    operator_display_name = "SR-IOV Network"

    SRIOV_NAMESPACE = "openshift-sriov-network-operator"
    SRIOV_OPERATOR_CONFIG_NAME = "default"
    OVS_CNI_ENV_VAR = "OVS_CNI_IMAGE"

    def run_rule(self):
        """Verify SriovOperatorConfig, operator pods, and the OVS-CNI subscription override."""
        errors = []
        errors.extend(self._verify_operator_config())
        errors.extend(self.validate_namespace_pods_health(self.SRIOV_NAMESPACE))
        errors.extend(self._verify_ovs_cni_override())

        if errors:
            return RuleResult.failed("\n\n".join(errors))

        return RuleResult.passed()

    def _verify_operator_config(self) -> list[str]:
        """Verify the SriovOperatorConfig exists with manageSoftwareBridges enabled.

        Returns:
            List of error messages. Empty list if the config is valid.
        """
        config = self.oc_api.select_single_resource(
            f"sriovoperatorconfig/{self.SRIOV_OPERATOR_CONFIG_NAME}",
            namespace=self.SRIOV_NAMESPACE,
        )
        if config is None:
            return [
                f"SriovOperatorConfig/{self.SRIOV_OPERATOR_CONFIG_NAME} not found "
                f"in {self.SRIOV_NAMESPACE} namespace"
            ]

        feature_gates = config.as_dict().get("spec", {}).get("featureGates", {})
        if not feature_gates.get("manageSoftwareBridges"):
            return [
                f"SriovOperatorConfig/{self.SRIOV_OPERATOR_CONFIG_NAME} has the "
                "manageSoftwareBridges feature gate disabled"
            ]

        return []

    def _verify_ovs_cni_override(self) -> list[str]:
        """Verify the operator subscription has the OVS_CNI_IMAGE env var override.

        Returns:
            List of error messages. Empty list if the override is present.
        """
        subscriptions_data = self.oc_api.get_operator_subscriptions()

        for sub in subscriptions_data.get("items", []):
            if sub.get("spec", {}).get("name") != self.operator_subscription_name:
                continue

            env_vars = sub.get("spec", {}).get("config", {}).get("env", [])
            if any(env.get("name") == self.OVS_CNI_ENV_VAR for env in env_vars):
                return []

            return [
                f"Subscription/{self.operator_subscription_name} is missing the "
                f"{self.OVS_CNI_ENV_VAR} environment variable override"
            ]

        return [f"Subscription/{self.operator_subscription_name} not found"]
