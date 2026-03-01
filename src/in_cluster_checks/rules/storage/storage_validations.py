"""
Storage validations ported from healthcheck-backup.

Direct port from: healthcheck-backup/HealthChecks/flows/Storage/ceph/Ceph.py
Adapted for OpenShift/OpenShift use case.
"""

import json

from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives


class CephRule(OrchestratorRule):
    """
    Base class for Ceph-related validation rules.

    Provides common functionality for all Ceph rules:
    - Prerequisite check for openshift-storage namespace
    - Ceph command detection (_get_ceph_command)

    Ported from CephValidation base class in healthcheck-backup.
    """

    def _get_ceph_pod(self) -> tuple:
        """
        Get the appropriate ceph pod for executing commands.

        For OpenShift with Rook-Ceph, we need to execute commands inside the
        rook-ceph-tools pod or ceph operator pod.

        Returns:
            Tuple of (namespace, pod_name, ceph_config_args)
            - namespace: Namespace where the pod is located
            - pod_name: Name of the pod
            - ceph_config_args: Additional ceph arguments (e.g., "-c /path/to/config" or "")
        """
        namespace = "openshift-storage"

        # First, try to find the rook-ceph-tools pod (preferred)
        pod_name = self._get_pod_name(namespace, {"app": "rook-ceph-tools"}, log_errors=False)
        if pod_name:
            return namespace, pod_name, ""

        # Fallback: use ceph operator pod (guaranteed to exist by prerequisite check)
        pod_name = self._get_pod_name(namespace, {"app": "rook-ceph-operator"})
        ceph_conf = "/var/lib/rook/openshift-storage/openshift-storage.config"
        return namespace, pod_name, f"-c {ceph_conf}"

    def _run_ceph_cmd(self, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
        """
        Execute a ceph command inside the appropriate pod.

        This helper method handles the common pattern of:
        1. Getting the ceph pod (tools or operator)
        2. Appending config args if using operator pod
        3. Executing the command via run_rsh_cmd

        Args:
            cmd: The ceph command to execute (e.g., "ceph health -f json")
            timeout: Command timeout in seconds (default: 30)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        namespace, pod_name, ceph_config_args = self._get_ceph_pod()

        if ceph_config_args:
            cmd += f" {ceph_config_args}"

        return self.run_rsh_cmd(namespace, pod_name, cmd, timeout=timeout)

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if Ceph is being used in the cluster.

        Verifies:
        1. openshift-storage namespace exists
        2. rook-ceph-operator pod exists (tools pod is optional)

        Returns:
            PrerequisiteResult indicating if Ceph storage is present
        """

        try:
            # Check if openshift-storage namespace exists (Rook-Ceph namespace)
            namespace_obj = self._select_resources(resource_type="namespace/openshift-storage", timeout=10, single=True)
            if not namespace_obj:
                return PrerequisiteResult.not_met(
                    "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
                )
        except Exception:
            return PrerequisiteResult.not_met(
                "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
            )

        # Check for operator pod (required - tools pod is optional)
        namespace = "openshift-storage"
        operator_pod = self._get_pod_name(namespace, {"app": "rook-ceph-operator"})

        if not operator_pod:
            return PrerequisiteResult.not_met(
                "No rook-ceph-operator pod found in openshift-storage namespace. Ceph operator is not running."
            )

        return PrerequisiteResult.met()


class CephOsdTreeWorks(CephRule):
    """
    Check if ceph osd tree command is working.

    This validation ensures that the Ceph cluster is accessible and the 'ceph osd tree'
    command executes successfully. This is a fundamental check for Ceph storage health.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "ceph_osd_tree_valid"
    title = "Check if ceph osd tree working"

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd("ceph osd tree")

        if return_code == 0:
            return RuleResult.passed()

        error_msg = "ceph osd tree is not working."
        if stderr:
            error_msg += f"\nError: {stderr}"
        if stdout:
            error_msg += f"\nOutput: {stdout}"
        return RuleResult.failed(error_msg)


class IsCephHealthOk(CephRule):
    """
    Check if ceph health is ok.

    This validation checks the overall health status of the Ceph cluster by running
    'ceph health -f json' and parsing the output. It verifies that the cluster status
    is HEALTH_OK and reports any health checks that are failing.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_ceph_health_ok"
    title = "Check if ceph health is ok"

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd("ceph health -f json")

        if return_code != 0:
            error_msg = "Failed to get ceph health status."
            if stderr:
                error_msg += f"\nError: {stderr}"
            if stdout:
                error_msg += f"\nOutput: {stdout}"
            return RuleResult.failed(error_msg)

        try:
            health_dict = json.loads(stdout)
        except json.JSONDecodeError as e:
            return RuleResult.failed(f"Failed to parse ceph health JSON output: {e}\nOutput: {stdout}")

        # Get status (handles both old and new ceph versions)
        status = health_dict.get("status") or health_dict.get("overall_status")

        if "HEALTH_OK" in status:
            return RuleResult.passed()

        # Ceph health is not OK - collect check details
        checks = {}

        if health_dict.get("checks"):
            # Newer ceph format
            for check in health_dict["checks"]:
                checks[check] = {
                    "severity": health_dict["checks"][check]["severity"],
                    "message": health_dict["checks"][check]["summary"]["message"],
                }
        elif health_dict.get("summary"):
            # Older ceph format
            for check in health_dict["summary"]:
                checks[check["summary"]] = {"severity": check["severity"]}

        error_msg = "Ceph health is not ok.\n" + json.dumps(checks, indent=4)
        return RuleResult.failed(error_msg)


class IsCephOSDsNearFull(CephRule):
    """
    Check if ceph OSDs disk usage is near full.

    This validation checks the disk utilization of all Ceph OSDs and reports any that are
    approaching full capacity. Uses two thresholds:
    - 80% utilization: WARNING severity
    - 90% utilization: CRITICAL severity (failed)
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_ceph_osds_near_full"
    title = "Check if ceph osds disk usage near full"

    THRESHOLD_WARNING = 80
    THRESHOLD_CRITICAL = 90

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd("ceph osd df -f json")

        if return_code != 0:
            error_msg = "Failed to get ceph osd df status."
            if stderr:
                error_msg += f"\nError: {stderr}"
            if stdout:
                error_msg += f"\nOutput: {stdout}"
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd df command")

        try:
            osd_df = json.loads(stdout)
        except json.JSONDecodeError as e:
            return RuleResult.failed(f"Failed to parse ceph osd df JSON output: {e}\nOutput: {stdout}")

        nodes = osd_df.get("nodes")
        if not nodes:
            return RuleResult.failed("No OSD nodes found in ceph osd df output")

        # Sort nodes by utilization (ascending)
        sorted_nodes = sorted(nodes, key=lambda x: float(x.get("utilization", 0)))

        # Collect problematic OSDs
        problematic_osds = []
        max_severity = None  # Track highest severity encountered

        for node in sorted_nodes:
            utilization = float(node.get("utilization", 0))

            if utilization <= self.THRESHOLD_WARNING:
                continue
            elif utilization > self.THRESHOLD_CRITICAL:
                max_severity = "CRITICAL"
                problematic_osds.append({"name": node.get("name", "unknown"), "utilization": utilization})
            else:
                # Between WARNING and CRITICAL thresholds
                if max_severity != "CRITICAL":
                    max_severity = "WARNING"
                problematic_osds.append({"name": node.get("name", "unknown"), "utilization": utilization})

        # All OSDs are under threshold
        if not problematic_osds:
            return RuleResult.passed()

        # Build error message
        error_msg = (
            "There are OSDs disk usage near or already over the limit.\n"
            "This indicates there is a risk ahead or already materialized, so need to react fast for ceph storage.\n"
            "Here is a list of problematic OSDs in this environment currently over limit:\n\n"
        )

        if max_severity == "CRITICAL":
            error_msg += f"Threshold: {self.THRESHOLD_CRITICAL}% (CRITICAL)\n\n"
        else:
            error_msg += f"Threshold: {self.THRESHOLD_WARNING}% (WARNING)\n\n"

        # Format OSD list
        error_msg += f"{'OSD Name':<15} {'Utilization':<15}\n"
        error_msg += "-" * 30 + "\n"
        for osd in problematic_osds:
            error_msg += f"{osd['name']:<15} {osd['utilization']:<15.2f}%\n"

        # Return appropriate result based on severity
        if max_severity == "CRITICAL":
            return RuleResult.failed(error_msg)
        else:
            return RuleResult.warning(error_msg)


class IsOSDsUp(CephRule):
    """
    Check if all OSDs in the cluster are up.

    This validation checks the status of all Ceph OSDs by running 'ceph osd tree -f json'
    and parsing the output to identify any OSDs that are in a down state.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_osds_up"
    title = "Check if all osds are up"

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd("ceph osd tree -f json")

        if return_code != 0:
            error_msg = "Failed to get ceph osd tree status."
            if stderr:
                error_msg += f"\nError: {stderr}"
            if stdout:
                error_msg += f"\nOutput: {stdout}"
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd tree command")

        try:
            osd_tree = json.loads(stdout)
        except json.JSONDecodeError as e:
            return RuleResult.failed(f"Failed to parse ceph osd tree JSON output: {e}\nOutput: {stdout}")

        nodes = osd_tree.get("nodes")
        if not nodes:
            return RuleResult.failed("No nodes found in ceph osd tree output")

        # Find all OSDs that are down
        # OSDs have type "osd", buckets (root, host, etc.) have other types
        down_osds = []
        for node in nodes:
            node_type = node.get("type")
            if node_type == "osd":
                status = node.get("status", "").lower()
                if status == "down":
                    osd_name = node.get("name", "unknown")
                    down_osds.append(osd_name)

        if down_osds:
            error_msg = f"The following OSDs are in down state: [{', '.join(down_osds)}]"
            return RuleResult.failed(error_msg)

        return RuleResult.passed()


class IsOSDsWeightOK(CephRule):
    """
    Check if OSD weights are within acceptable range.

    This validation verifies that each OSD's CRUSH weight is within the acceptable
    range (±5%) of its calculated weight based on disk size. OSDs with weights
    significantly different from expected values can impact cluster performance
    and data distribution.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_osds_weight_ok"
    title = "Check if osds weight are within the ceph recommendation margins"

    ACCEPTABLE_RANGE = 0.05  # 5% tolerance

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd("ceph osd df -f json")

        if return_code != 0:
            error_msg = "Failed to get ceph osd df status."
            if stderr:
                error_msg += f"\nError: {stderr}"
            if stdout:
                error_msg += f"\nOutput: {stdout}"
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd df command")

        try:
            osd_df = json.loads(stdout)
        except json.JSONDecodeError as e:
            return RuleResult.failed(f"Failed to parse ceph osd df JSON output: {e}\nOutput: {stdout}")

        nodes = osd_df.get("nodes")
        if not nodes:
            return RuleResult.failed("No nodes found in ceph osd df output")

        # Check each OSD's weight
        problematic_osds = []
        for node in nodes:
            osd_id = str(node.get("id", "unknown"))
            osd_size_kb = int(node.get("kb", 0))
            current_weight = float(node.get("crush_weight", 0))

            # Calculate expected weight (KB to TB conversion)
            calculated_weight = self._convert_kb_to_tb(osd_size_kb)

            # Calculate acceptable range
            max_acceptable = calculated_weight * (1 + self.ACCEPTABLE_RANGE)
            min_acceptable = calculated_weight * (1 - self.ACCEPTABLE_RANGE)

            # Check if current weight is outside acceptable range
            if not (min_acceptable < current_weight < max_acceptable):
                if min_acceptable == 0 and max_acceptable == 0:
                    # Special case: OSD size is 0
                    problematic_osds.append(
                        {
                            "osd_id": osd_id,
                            "current_weight": current_weight,
                            "issue": "OSD size is 0",
                        }
                    )
                else:
                    problematic_osds.append(
                        {
                            "osd_id": osd_id,
                            "current_weight": current_weight,
                            "min_acceptable": round(min_acceptable, 4),
                            "max_acceptable": round(max_acceptable, 4),
                        }
                    )

        if not problematic_osds:
            return RuleResult.passed()

        # Build warning message
        error_msg = "The following OSDs weight not in acceptable range:\n\n"

        for osd in problematic_osds:
            if osd.get("issue"):
                error_msg += f"OSD '{osd['osd_id']}' - current weight is {osd['current_weight']}, but {osd['issue']}\n"
            else:
                error_msg += (
                    f"OSD '{osd['osd_id']}' - current weight is {osd['current_weight']}, "
                    f"while it should be greater than {osd['min_acceptable']} "
                    f"and smaller than {osd['max_acceptable']}\n"
                )

        return RuleResult.warning(error_msg.rstrip())

    def _convert_kb_to_tb(self, kb_value: int) -> float:
        """Convert KB to TB."""
        return float(kb_value / 1024 / 1024 / 1024)
