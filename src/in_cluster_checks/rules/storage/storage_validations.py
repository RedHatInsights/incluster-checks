"""
Storage validations ported from healthcheck-backup.

Direct port from: healthcheck-backup/HealthChecks/flows/Storage/ceph/Ceph.py
Adapted for OpenShift/OpenShift use case.
"""

import json
import re
from datetime import datetime, timezone

from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_int, parse_json


class CephRule(OrchestratorRule):
    """
    Base class for Ceph-related validation rules.

    Provides common functionality for all Ceph rules:
    - Prerequisite check for openshift-storage namespace
    - Ceph command detection (_get_ceph_command)

    Ported from CephValidation base class in healthcheck-backup.
    """

    NAMESPACE = "openshift-storage"

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
        # First, try to find the rook-ceph-tools pod (preferred)
        pod_name = self._get_pod_name(self.NAMESPACE, {"app": "rook-ceph-tools"}, log_errors=False)
        if pod_name:
            return self.NAMESPACE, pod_name, ""

        # Fallback: use ceph operator pod (guaranteed to exist by prerequisite check)
        pod_name = self._get_pod_name(self.NAMESPACE, {"app": "rook-ceph-operator"})
        ceph_conf = f"/var/lib/rook/{self.NAMESPACE}/{self.NAMESPACE}.config"
        return self.NAMESPACE, pod_name, f"-c {ceph_conf}"

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
        operator_pod = self._get_pod_name(self.NAMESPACE, {"app": "rook-ceph-operator"})

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

        error_msg = self.build_cmd_error_message("ceph osd tree is not working.", stdout, stderr)
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
        cmd = "ceph health -f json"
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
        cmd = "ceph osd df -f json"
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
        cmd = "ceph osd tree -f json"
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to get ceph osd tree status.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph osd tree command")

        osd_tree = parse_json(stdout, cmd, self.get_host_ip())

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
        cmd = "ceph osd df -f json"
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


class OrphanCsiVolumes(CephRule):
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
        rc, stdout, stderr = self.run_oc_command("get", ["pv", "-o", f"jsonpath={jsonpath}"])

        # Parse space-separated subvolume names, filter out empty values
        return set(name for name in stdout.split() if name)

    def _get_ceph_subvolume_list(self):
        """
        Get all CSI subvolumes from Ceph filesystem.

        Returns:
            List of CSI subvolume names or RuleResult if operation failed
        """
        cmd = "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json"
        return_code, stdout, stderr = self._run_ceph_cmd(cmd)

        if return_code != 0:
            error_msg = self.build_cmd_error_message("Failed to list CSI subvolumes from Ceph.", stdout, stderr)
            return RuleResult.failed(error_msg)

        if not stdout:
            return RuleResult.failed("Empty results from ceph fs subvolume ls command")

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


class OsdJournalError(CephRule):
    """
    Check if OSDs had journal errors in the last hour.

    This validation checks for OSD pods that have failed or restarted in the last hour,
    indicating potential journal errors or other issues. It examines pod status, restart
    counts, and logs to identify problematic OSDs.

    Ported from HealthChecks OsdJournalError rule, adapted for OpenShift/Rook-Ceph.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "osd_journal_errors_last_hour"
    title = "Check if OSDs had journal errors in the last hour"

    def run_rule(self) -> RuleResult:
        osd_pods = self._get_osd_pods()
        if not osd_pods:
            return RuleResult.failed(f"No OSD pods found in {self.NAMESPACE} namespace")

        problematic_osds = []
        for pod in osd_pods:
            osd_info = self._check_pod_health(pod)
            if osd_info:
                problematic_osds.append(osd_info)

        if not problematic_osds:
            return RuleResult.passed()

        error_msg = self._build_error_message(problematic_osds)
        return RuleResult.failed(error_msg)

    def _get_osd_pods(self) -> list:
        """Get all OSD pods from the cluster."""
        return self._get_pods(namespace=self.NAMESPACE, labels={"app": "rook-ceph-osd"})

    def _check_pod_health(self, pod) -> dict | None:
        """
        Check if a pod has health issues and collect diagnostics.

        Args:
            pod: Pod object from openshift_client

        Returns:
            Dictionary with pod info if problematic, None otherwise
        """
        pod_name = pod.name()
        pod_status = pod.model.status.phase
        container_statuses = pod.model.status.containerStatuses or []

        has_recent_restarts, container_errors = self._get_recent_restarts_and_errors(container_statuses)

        if not self._is_osd_problematic(pod_status, has_recent_restarts, container_errors):
            return None

        osd_id = self._extract_osd_id(pod)

        # Get pod logs using oc logs command
        return_code, log_output, stderr = self.run_oc_command(
            "logs",
            ["-n", self.NAMESPACE, pod_name, "--since=1h", "--tail=15"],
            timeout=30,
            raise_on_error=False,
        )

        if return_code != 0:
            self.logger.warning(f"Failed to get logs for pod {self.NAMESPACE}/{pod_name}: {stderr}")
            log_output = ""

        return {
            "pod_name": pod_name,
            "osd_id": osd_id,
            "status": pod_status,
            "container_errors": container_errors,
            "logs": log_output,
        }

    def _get_recent_restarts_and_errors(self, container_statuses: list) -> tuple[bool, list]:
        """
        Check for recent restarts and error states in container statuses.

        Checks if any containers have restarted in the last hour by examining the
        lastState.finishedAt timestamp.

        Args:
            container_statuses: List of container status objects

        Returns:
            Tuple of (has_recent_restarts, list_of_container_errors)
        """
        has_recent_restarts = False
        container_errors = []
        now = datetime.now(timezone.utc)

        for container in container_statuses:
            # Check if container restarted in the last hour
            if container.lastState and container.lastState.terminated:
                finished_at = container.lastState.terminated.finishedAt
                if finished_at:
                    # Parse the timestamp (format: "2025-02-26T10:15:30Z")
                    try:
                        finished_time = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                        time_diff = (now - finished_time).total_seconds()
                        if time_diff <= 3600:  # 1 hour = 3600 seconds
                            has_recent_restarts = True
                    except (ValueError, AttributeError):
                        # If we can't parse the timestamp, skip this check
                        pass

            # Check if container is in error state
            if container.state.waiting and container.state.waiting.reason in [
                "CrashLoopBackOff",
                "Error",
                "ImagePullBackOff",
            ]:
                container_errors.append(
                    f"{container.name}: {container.state.waiting.reason} - {container.state.waiting.message or ''}"
                )
            elif container.state.terminated and container.state.terminated.reason in ["Error", "OOMKilled"]:
                container_errors.append(
                    f"{container.name}: {container.state.terminated.reason} - "
                    f"{container.state.terminated.message or ''}"
                )

        return has_recent_restarts, container_errors

    def _is_osd_problematic(self, pod_status: str, has_recent_restarts: bool, container_errors: list) -> bool:
        """
        Determine if OSD pod is problematic.

        An OSD is considered problematic if:
        1. Pod is not in Running state, OR
        2. Pod has restarted in the last hour, OR
        3. Container has errors

        Args:
            pod_status: Pod phase (Running, Pending, Failed, etc.)
            has_recent_restarts: True if any container restarted in the last hour
            container_errors: List of container error strings

        Returns:
            True if OSD is problematic, False otherwise
        """
        return pod_status != "Running" or has_recent_restarts or bool(container_errors)

    def _extract_osd_id(self, pod) -> str:
        """
        Extract OSD ID from pod labels or name.

        Args:
            pod: Pod object from openshift_client

        Returns:
            OSD ID as string, or "unknown" if not found
        """
        osd_id = pod.model.metadata.labels.get("ceph-osd-id", "unknown")
        if osd_id == "unknown":
            # Try to extract from pod name (format: rook-ceph-osd-<ID>-<hash>-<suffix>)
            # Example: rook-ceph-osd-0-5fc8f487b4-2w5qb
            match = re.search(r"rook-ceph-osd-(\d+)-[a-z0-9]+-[a-z0-9]+", pod.name())
            if match:
                osd_id = match.group(1)
        return osd_id

    def _build_error_message(self, problematic_osds: list) -> str:
        """
        Build formatted error message from problematic OSDs.

        Args:
            problematic_osds: List of OSD info dictionaries

        Returns:
            Formatted error message string
        """
        error_parts = []
        for osd in problematic_osds:
            part = f"Pod Name: {osd['pod_name']}\n"
            part += f"OSD ID: {osd['osd_id']}\n"
            part += f"Status: {osd['status']}\n"

            if osd["container_errors"]:
                part += "Container Errors:\n"
                for error in osd["container_errors"]:
                    part += f"  - {error}\n"

            if osd["logs"]:
                part += f"Recent Logs (last 15 lines or 1 hour):\n{osd['logs']}\n"

            error_parts.append(part)

        return "\n\n".join(error_parts)
