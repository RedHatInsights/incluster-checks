"""
Storage validations ported from healthcheck-backup.

Direct port from: healthcheck-backup/HealthChecks/flows/Storage/ceph/Ceph.py
Adapted for OpenShift/OpenShift use case.
"""

import json

from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_int, parse_json
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class CephRule(OrchestratorRule):
    """
    Base class for Ceph-related validation rules.

    Provides common functionality for all Ceph rules:
    - Prerequisite check for openshift-storage namespace and rook-ceph-operator
    - Ceph command execution helpers (_run_ceph_cmd)
    - External mode detection (_is_external_ceph_mode)

    Subclasses should use CephAccessRule (for rules that need Ceph CLI access
    in both internal and external modes) or InternalCephRule (for rules that
    only apply to internal Ceph mode).
    """

    NAMESPACE = "openshift-storage"

    def _parse_osd_tree(self) -> tuple[list[str], list[str]] | RuleResult:
        """Parse ceph osd tree. Returns (down_osd_names, all_osd_names) or RuleResult on error."""
        cmd = SafeCmdString("ceph osd tree -f json")
        rc, stdout, stderr = self._run_ceph_cmd(cmd)

        if rc != 0:
            return RuleResult.failed(
                self.build_cmd_error_message("Failed to get ceph osd tree status.", stdout, stderr)
            )

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd tree command")

        osd_tree = parse_json(stdout, cmd, self.get_host_ip())
        if not isinstance(osd_tree, dict):
            return RuleResult.failed("Invalid results from ceph osd tree command")

        nodes = osd_tree.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return RuleResult.failed("No nodes found in ceph osd tree output")
        if not all(isinstance(node, dict) for node in nodes):
            return RuleResult.failed("Invalid results from ceph osd tree command")

        osd_nodes = [n for n in nodes if n.get("type") == "osd"]
        down = [n.get("name", "unknown") for n in osd_nodes if n.get("status", "").lower() == "down"]
        all_names = [n.get("name", "unknown") for n in osd_nodes]
        return down, all_names

    def _get_down_osds(self) -> list[str] | RuleResult:
        """Get list of down OSDs from ceph osd tree.

        Returns:
            List of down OSD names (empty if all are up), or
            RuleResult.failed if the ceph command fails
        """
        result = self._parse_osd_tree()
        if isinstance(result, RuleResult):
            return result
        down, _ = result
        return down

    def _is_external_ceph_mode(self) -> bool:
        """
        Detect if Ceph is running in external mode.

        External mode is identified by the absence of both rook-ceph-osd pods and
        rook-ceph-osd-prepare jobs. In external mode, the Ceph cluster runs outside
        OpenShift (OSDs are external), and only CSI drivers and operators run in-cluster.

        In internal mode, OSD pods run in the openshift-storage namespace. Checking only
        OSD pods misses clusters where all OSD provisioning failed (no pods yet but jobs exist).

        Returns:
            True if external Ceph mode is detected, False otherwise
        """
        try:
            if self.oc_api.get_pod_name(self.NAMESPACE, {"app": "rook-ceph-osd"}, log_errors=False):
                return False
            has_prepare_jobs = bool(
                self.oc_api.select_resources("job", namespace=self.NAMESPACE, labels={"app": "rook-ceph-osd-prepare"})
            )
            return not has_prepare_jobs
        except Exception:
            return False

    def _run_ceph_cmd(self, cmd: SafeCmdString, timeout: int = 30) -> tuple[int, str, str]:
        """
        Execute a ceph command inside the appropriate pod.

        This helper method handles the common pattern of:
        1. Getting the ceph pod (tools or operator)
        2. Appending config args if using operator pod
        3. Executing the command via run_rsh_cmd

        Args:
            cmd: SafeCmdString with the ceph command to execute
            timeout: Command timeout in seconds (default: 30)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        # First, try to find the rook-ceph-tools pod (preferred)
        pod_name = self.oc_api.get_pod_name(self.NAMESPACE, {"app": "rook-ceph-tools"}, log_errors=False)
        if pod_name:
            # Tools pod doesn't need config file
            return self.oc_api.run_rsh_cmd(self.NAMESPACE, pod_name, cmd, timeout=timeout)

        # Fallback: use ceph operator pod (guaranteed to exist by prerequisite check)
        pod_name = self.oc_api.get_pod_name(self.NAMESPACE, {"app": "rook-ceph-operator"})
        ceph_conf = f"/var/lib/rook/{self.NAMESPACE}/{self.NAMESPACE}.config"
        # Append config file path to command (pass SafeCmdString directly for composition)
        cmd_with_config = SafeCmdString("{cmd} -c {conf}").format(cmd=cmd, conf=ceph_conf)
        return self.oc_api.run_rsh_cmd(self.NAMESPACE, pod_name, cmd_with_config, timeout=timeout)

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if Ceph is being used in the cluster.
        Verifies:
        1. openshift-storage namespace exists
        2. rook-ceph-operator pod exists

        Returns:
            PrerequisiteResult indicating if Ceph storage is present
        """

        try:
            # Check if openshift-storage namespace exists (Rook-Ceph namespace)
            namespace_obj = self.oc_api.select_single_resource(resource_type="namespace/openshift-storage", timeout=10)
            if not namespace_obj:
                return PrerequisiteResult.not_met(
                    "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
                )
        except Exception:
            return PrerequisiteResult.not_met(
                "OpenShift Storage namespace not found. Ceph is not deployed in this cluster."
            )

        # Check for operator pod (required)
        operator_pod = self.oc_api.get_pod_name(self.NAMESPACE, {"app": "rook-ceph-operator"}, log_errors=False)

        if not operator_pod:
            return PrerequisiteResult.not_met(
                "No rook-ceph-operator pod found in openshift-storage namespace. Ceph operator is not running."
            )

        return PrerequisiteResult.met()


class CephAccessRule(CephRule):
    """
    Base class for Ceph rules that require CLI access to the Ceph cluster.

    Works in both internal and external Ceph modes. In external mode, the
    rook-ceph-tools pod must be present to execute Ceph commands since
    the operator pod alone cannot reach the external cluster.

    Use this base class for rules that run Ceph CLI commands (ceph health,
    ceph osd tree, etc.) and need to work regardless of deployment mode.
    """

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check base Ceph prerequisites and verify Ceph CLI access.

        Verifies:
        1. Base Ceph prerequisites (namespace + operator)
        2. For external Ceph mode: rook-ceph-tools pod must exist

        Returns:
            PrerequisiteResult indicating if Ceph CLI access is available
        """
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result

        if self._is_external_ceph_mode():
            tools_pod = self.oc_api.get_pod_name(self.NAMESPACE, {"app": "rook-ceph-tools"}, log_errors=False)

            if not tools_pod:
                return PrerequisiteResult.not_met(
                    "External Ceph detected. To run Ceph health checks, consider enabling the Ceph toolbox "
                    "(set spec.enableCephTools=true in the StorageCluster resource)."
                )

        return PrerequisiteResult.met()


class CephOsdTreeWorks(CephAccessRule):
    """
    Check if ceph osd tree command is working.

    This validation ensures that the Ceph cluster is accessible and the 'ceph osd tree'
    command executes successfully. This is a fundamental check for Ceph storage health.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "ceph_osd_tree_valid"
    title = "Check if ceph osd tree working"

    def run_rule(self) -> RuleResult:
        return_code, stdout, stderr = self._run_ceph_cmd(SafeCmdString("ceph osd tree"))

        if return_code == 0:
            return RuleResult.passed()

        error_msg = self.build_cmd_error_message("ceph osd tree is not working.", stdout, stderr)
        return RuleResult.failed(error_msg)


class IsCephHealthOk(CephAccessRule):
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
        cmd = SafeCmdString("ceph health -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph health status.", stdout, stderr)
            return RuleResult.failed(error_msg)

        health_dict = parse_json(stdout, cmd, self.get_host_ip())

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


class IsCephOSDsNearFull(CephAccessRule):
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
        cmd = SafeCmdString("ceph osd df -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph osd df status.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd df command")

        osd_df = parse_json(stdout, cmd, self.get_host_ip())

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


class IsOSDsUp(CephAccessRule):
    """
    Check if all OSDs in the cluster are up.

    This validation checks the status of all Ceph OSDs by running 'ceph osd tree -f json'
    and parsing the output to identify any OSDs that are in a down state.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "is_osds_up"
    title = "Check if all osds are up"

    def run_rule(self) -> RuleResult:
        down_osds = self._get_down_osds()
        if isinstance(down_osds, RuleResult):
            return down_osds

        if down_osds:
            return RuleResult.failed(f"The following OSDs are in down state: [{', '.join(down_osds)}]")

        return RuleResult.passed()


class IsOSDsWeightOK(CephAccessRule):
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
        cmd = SafeCmdString("ceph osd df -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph osd df status.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd df command")

        osd_df = parse_json(stdout, cmd, self.get_host_ip())

        nodes = osd_df.get("nodes")
        if not nodes:
            return RuleResult.failed("No nodes found in ceph osd df output")

        # Check each OSD's weight
        problematic_osds = []
        for node in nodes:
            osd_id = str(node.get("id", "unknown"))
            osd_size_kb = parse_int(node.get("kb", 0), cmd, self.get_host_ip())
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


class OrphanCsiVolumes(CephAccessRule):
    """
    Check for orphaned Ceph CSI volumes.

    This validation identifies CSI subvolumes that exist in the Ceph storage backend
    but have no corresponding PersistentVolume in OpenShift. These orphaned volumes
    consume storage space but are not accessible to the cluster and may indicate
    incomplete cleanup after PV deletion.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "orphan_csi_volumes"
    title = "Check for orphaned Ceph CSI volumes"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if CephFS CSI subvolume group exists.

        Returns:
            PrerequisiteResult indicating if CSI storage is configured
        """
        # First check base Ceph prerequisites (namespace, operator, tools)
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result

        # Check if ceph filesystem exists
        cmd = SafeCmdString("ceph fs ls -f json")
        return_code, stdout, _ = self._run_ceph_cmd(cmd)

        if return_code != 0:
            return PrerequisiteResult.not_met("Cannot query Ceph filesystems")

        filesystems = parse_json(stdout, cmd, self.get_host_ip())
        has_cephfs = any(fs.get("name") == "ocs-storagecluster-cephfilesystem" for fs in filesystems)

        if not has_cephfs:
            return PrerequisiteResult.not_met("CephFS filesystem 'ocs-storagecluster-cephfilesystem' not found")

        # Check if CSI subvolume group exists
        cmd = SafeCmdString("ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            return PrerequisiteResult.not_met(f"Cannot query Ceph subvolume groups: {stderr}")

        groups = parse_json(stdout, cmd, self.get_host_ip())
        has_csi_group = any(group.get("name") == "csi" for group in groups)

        if not has_csi_group:
            return PrerequisiteResult.not_met(
                "CSI subvolume group does not exist. No CephFS PVCs have been created yet."
            )

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        pv_subvolumes = self._get_pv_subvolume_names()

        csi_subvolumes_result = self._get_ceph_subvolume_list()
        if isinstance(csi_subvolumes_result, RuleResult):
            return csi_subvolumes_result
        # Find orphans - volumes in Ceph but not in PVs
        orphans = [vol for vol in csi_subvolumes_result if vol not in pv_subvolumes]

        if not orphans:
            return RuleResult.passed()

        error_msg = (
            f"Found {len(orphans)} orphaned CSI volume(s) in Ceph storage.\n"
            "These volumes exist in the storage backend but have no corresponding PersistentVolume.\n"
            "They may be consuming storage space and could be candidates for cleanup.\n\n"
            f"Total PVs with CSI volumes: {len(pv_subvolumes)}\n"
            f"Total CSI subvolumes in Ceph: {len(csi_subvolumes_result)}\n"
            f"Orphaned volumes: {len(orphans)}\n\n"
            "Orphaned CSI volume names:\n"
        )

        for orphan in sorted(orphans):
            error_msg += f"  - {orphan}\n"

        return RuleResult.failed(error_msg.rstrip())

    def _get_pv_subvolume_names(self):
        """
        Get all CSI subvolume names from PersistentVolumes.

        Returns:
            Set of subvolume names, or RuleResult if operation failed
        """
        jsonpath = "{.items[*].spec.csi.volumeAttributes.subvolumeName}"
        rc, stdout, stderr = self.oc_api.run_oc_command("get", ["pv", "-o", f"jsonpath={jsonpath}"])

        # Parse space-separated subvolume names, filter out empty values
        return set(name for name in stdout.split() if name)

    def _get_ceph_subvolume_list(self):
        """
        Get all CSI subvolumes from Ceph filesystem.

        Returns:
            List of CSI subvolume names or RuleResult if operation failed
        """
        cmd = SafeCmdString("ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            # Check if error is "subvolume group does not exist"
            if "does not exist" in stderr or "ENOENT" in stderr:
                # This should be caught by prerequisite, but handle gracefully if it reaches here
                return []

            error_msg = self.build_cmd_error_message("Failed to list CSI subvolumes from Ceph.", stdout, stderr)
            return RuleResult.failed(error_msg)

        # Empty or [] is valid - no subvolumes exist yet
        if not stdout or stdout.strip() in ("", "[]"):
            return []

        subvolumes_data = parse_json(stdout, cmd, self.get_host_ip())

        # Extract subvolume names from the array
        # Each entry is like: {"name": "csi-vol-abc123"}
        subvolume_names = []
        for entry in subvolumes_data:
            if isinstance(entry, dict):
                name = entry.get("name")
                if name:
                    subvolume_names.append(name)

        return subvolume_names


class CephSlowOps(CephAccessRule):
    """
    Check if ceph has slow ops.

    This validation checks for slow or blocked operations in the Ceph cluster by running
    'ceph health detail' and looking for SLOW_OPS warnings. Slow ops can indicate
    bad media, cluster saturation, or networking issues.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "ceph_slow_ops"
    title = "Check if ceph has slow ops"

    def run_rule(self) -> RuleResult:
        cmd = SafeCmdString("ceph health detail")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd, timeout=100)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph health detail.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if "SLOW_OPS" in stdout or "REQUEST_SLOW" in stdout:
            return RuleResult.warning(
                "There are slow ops observed on this cluster. "
                "Blocked/Slow ops can have numerous possible root causes from bad media, "
                "cluster saturation and networking issues."
            )

        return RuleResult.passed()


class CheckPoolSize(CephAccessRule):
    """
    Check if ceph replication factor is at least 2 for all pools.

    This validation checks each Ceph pool's replication factor (size) and reports
    any pools with a replication factor less than 2, indicating a risk of no high
    availability.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "check_ceph_replication_factor_is_at_least_2"
    title = "Check ceph replication factor is at least 2"

    def run_rule(self) -> RuleResult:
        cmd = SafeCmdString("ceph osd pool ls detail -f json")
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph pool details.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd pool ls detail command")

        pools = parse_json(stdout, cmd, self.get_host_ip())

        problematic_pools = []
        for pool in pools:
            if pool["size"] < 2:
                problematic_pools.append(pool["pool_name"])

        if problematic_pools:
            return RuleResult.warning(
                "ceph replication factor is less than 2 in following pools:\n" + "\n".join(problematic_pools)
            )

        return RuleResult.passed()
