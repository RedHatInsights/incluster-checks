"""
NMState NodeNetworkConfigurationPolicy validation for OpenShift clusters.

Validates that all NodeNetworkConfigurationPolicy (NNCP) resources are in a healthy state
after cluster operations like node reboots.
"""

from typing import Dict, List

import openshift_client as oc

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives


class VerifyAllNNCPsAvailable(OrchestratorRule):
    """
    Verify all NodeNetworkConfigurationPolicies are Available.

    This check validates that all NNCP resources are in a healthy state by checking:
    - Available condition must be True
    - Degraded condition must NOT be True
    - Progressing condition must NOT be True

    This is a critical health check after node reboots to ensure network
    configurations have been properly applied.

    Reference:
        eco-gotests rdscore/internal/rdscorecommon/nmstate-validation.go
    """

    unique_name = "verify_all_nncps_available"
    title = "Verify all NodeNetworkConfigurationPolicies are Available"
    supported_profiles = {"telco-base"}
    objective_hosts = [Objectives.ORCHESTRATOR]
    links = [
        "https://github.com/RedHatInsights/incluster-checks/wiki/"
        "Network-%E2%80%90-Verify-all-NodeNetworkConfigurationPolicies-are-Available",
    ]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if NMState operator is installed.

        Returns:
            PrerequisiteResult indicating if NMState CRD exists
        """
        try:
            # Check if NNCP CRD exists by attempting to list resources
            self.oc_api.select_resources("nodenetworkconfigurationpolicies", all_namespaces=True, timeout=30)
            # If select_resources succeeds, CRD exists (even if no instances found)
            return PrerequisiteResult.met()
        except oc.OpenShiftPythonException as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "no matches for kind" in error_msg:
                return PrerequisiteResult.not_met("NMState operator is not installed (NNCP CRD not found)")
            # Re-raise other OpenShift errors (timeouts, RBAC, etc.) to propagate naturally
            raise

    def run_rule(self) -> RuleResult:
        """
        Verify all NNCPs are in healthy state.

        Returns:
            RuleResult indicating NNCP health status
        """
        nncps = self.oc_api.select_resources("nodenetworkconfigurationpolicies", all_namespaces=True, timeout=60)

        if not nncps:
            return RuleResult.not_applicable("No NodeNetworkConfigurationPolicies found")

        failed_nncps = self._check_nncp_conditions(nncps)

        if failed_nncps:
            message = "NodeNetworkConfigurationPolicies are not healthy:\n" + "\n".join(failed_nncps)
            return RuleResult.failed(message)

        return RuleResult.passed(f"All {len(nncps)} NodeNetworkConfigurationPolicies are healthy")

    def _check_nncp_conditions(self, nncps: List) -> List[str]:
        """
        Check NNCP status conditions.

        Args:
            nncps: List of NNCP resource objects

        Returns:
            List of error messages for failed NNCPs
        """
        failed_checks = []

        for nncp in nncps:
            # Validate required metadata field
            if not hasattr(nncp, "model") or not hasattr(nncp.model, "metadata"):
                raise UnExpectedSystemOutput(
                    f"NNCP object missing required 'model.metadata' structure: {nncp}"
                )
            if not hasattr(nncp.model.metadata, "name"):
                raise UnExpectedSystemOutput(
                    f"NNCP object missing required 'model.metadata.name' field: {nncp.model.metadata}"
                )

            nncp_name = nncp.model.metadata.name
            conditions = self._get_conditions(nncp)

            if not conditions:
                failed_checks.append(f"  - {nncp_name}: No status conditions found")
                continue

            # Check each condition type
            condition_failures = self._validate_conditions(nncp_name, conditions)
            failed_checks.extend(condition_failures)

        return failed_checks

    def _get_conditions(self, nncp) -> List[Dict]:
        """
        Extract status conditions from NNCP.

        Args:
            nncp: NNCP resource object

        Returns:
            List of condition dictionaries
        """
        if hasattr(nncp.model, "status") and hasattr(nncp.model.status, "conditions"):
            return nncp.model.status.conditions or []
        return []

    def _validate_conditions(self, nncp_name: str, conditions: List[Dict]) -> List[str]:
        """
        Validate NNCP status conditions.

        Args:
            nncp_name: Name of the NNCP
            conditions: List of condition dictionaries

        Returns:
            List of failure messages
        """
        failures = []

        # Build condition map and validate structure
        condition_map = {}
        for cond in conditions:
            if not hasattr(cond, "type"):
                raise UnExpectedSystemOutput(
                    f"NNCP {nncp_name} condition missing required 'type' field: {cond}"
                )
            if not hasattr(cond, "status"):
                raise UnExpectedSystemOutput(
                    f"NNCP {nncp_name} condition missing required 'status' field: {cond}"
                )
            condition_map[cond.type] = cond

        # Check Available condition
        available_cond = condition_map.get("Available")
        if not available_cond or available_cond.status != "True":
            message = available_cond.message if available_cond else "condition not found"
            failures.append(f"  - {nncp_name}: Not Available ({message})")

        # Check Degraded condition (should NOT be True)
        degraded_cond = condition_map.get("Degraded")
        if degraded_cond and degraded_cond.status == "True":
            failures.append(f"  - {nncp_name}: Degraded ({degraded_cond.message})")

        # Check Progressing condition (should NOT be True)
        progressing_cond = condition_map.get("Progressing")
        if progressing_cond and progressing_cond.status == "True":
            failures.append(f"  - {nncp_name}: Still Progressing ({progressing_cond.message})")

        return failures
