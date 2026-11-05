import re
from datetime import datetime, timezone

from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.rules.storage.storage_validations import CephRule
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_json


class InternalCephRule(CephRule):
    """
    Base class for Ceph rules that only apply to internal Ceph mode.

    Internal mode means OSD pods run within the openshift-storage namespace.
    Rules inheriting from this class are skipped when external Ceph is detected
    because the resources they check (e.g. OSD prepare pods) do not exist in
    external mode.
    """

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result

        if self._is_external_ceph_mode():
            return PrerequisiteResult.not_met(
                "This rule applies only to internal Ceph mode. "
                "External Ceph detected - OSD prepare pods are not present in external mode."
            )

        return PrerequisiteResult.met()


class OsdPrepareJobHealth(InternalCephRule):
    """
    Check for stuck or orphaned OSD prepare jobs.

    Active jobs (status.active > 0) are flagged when:
    1. Job has no 'ceph.rook.io/pvc' label and is not explicitly host-backed.
       PVC-backed jobs report a missing mapping; unknown storage reports incomplete validation.
    2. Job's PVC already has an OSD deployment — device is claimed.
    3. Job's PVC is Pending — no matching local PV is available (more PVCs than pre-provisioned PVs exist).
       Only checked when the storage class uses kubernetes.io/no-provisioner (local storage backed by
       openshift-local-storage-operator), where a Pending PVC will not resolve on its own and indicates
       a configuration issue (e.g. Add Capacity used without sufficient available PVs).
       Skipped for dynamic provisioners, where PVCs may be transiently Pending during PV creation.

    Exhausted jobs (status.conditions contains Failed=True, no active pods) are flagged when:
    4. Job exhausted its backoffLimit with no OSD deployment — OSD provisioning permanently failed.
       Skipped if an OSD deployment exists for the PVC: preparation progressed to deployment creation.
       Deployment availability is outside this rule; later OSD outages must not revive historical job failures.

    Succeeded jobs (status.succeeded > 0) are flagged when:
    5. Job completed cleanly but no OSD deployment exists for its PVC — Rook silently skipped the
       device. Container termination messages are included as diagnostic context when available.
       The per-PVC status ConfigMap (rook-ceph-osd-<pvc>-status) distinguishes race windows from
       confirmed skips. The prepare pod writes 'completed' and the provisioned OSDs to it before
       exiting, so it always exists when a job succeeds.
       ConfigMap present, osds non-empty → Rook is mid-reconcile and will create the OSD deployment.
           Silently skipped unless the Rook operator pod is not Running/Ready, which indicates Rook
           has stalled and will never process the job — reported as a failure.
       ConfigMap present, osds empty → pod ran but skipped the device — confirmed skip — reported as a failure.
       ConfigMap absent → operator processed the job, found no OSDs to create, and deleted it
           (confirmed skip) — reported as a failure.

    Reference: https://access.redhat.com/solutions/7057329
    """

    PVC_LABEL = "ceph.rook.io/pvc"
    PVC_NOT_FOUND = "not found"
    OSD_STATUS_CONFIGMAP_PREFIX = "rook-ceph-osd-"
    OSD_STATUS_CONFIGMAP_SUFFIX = "-status"
    LOCAL_STORAGE_PROVISIONER = "kubernetes.io/no-provisioner"

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "osd_prepare_job_health"
    title = "Check OSD prepare jobs health"
    links = [
        "https://access.redhat.com/solutions/7057329",
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/486801529",
    ]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result

        if not self._get_prepare_jobs():
            return PrerequisiteResult.not_met("No rook-ceph-osd-prepare jobs found in openshift-storage namespace.")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        jobs = self._get_prepare_jobs()
        active_jobs = [j for j in jobs if self._is_job_active(j)]
        exhausted_jobs = [j for j in jobs if not self._is_job_active(j) and self._is_job_failed(j)]
        succeeded_jobs = [j for j in jobs if self._is_job_succeeded(j)]
        if not active_jobs and not exhausted_jobs and not succeeded_jobs:
            return RuleResult.passed()

        all_pvc_names = {
            n
            for job in active_jobs + exhausted_jobs + succeeded_jobs
            if (n := job.model.metadata.labels.get(self.PVC_LABEL, ""))
        }
        claimed_osd_pvcs: set[str] = set()
        pvc_phases: dict[str, str | None] = {}
        if all_pvc_names:
            claimed_osd_pvcs = self._get_claimed_osd_pvcs()
            pvc_names_to_check = all_pvc_names - claimed_osd_pvcs
            pvc_phases = self._get_pvc_phases(pvc_names_to_check) if pvc_names_to_check else {}

        issues = []

        issues.extend(self._check_active_jobs(active_jobs, claimed_osd_pvcs, pvc_phases))
        issues.extend(self._check_exhausted_jobs(exhausted_jobs, claimed_osd_pvcs, pvc_phases))
        issues.extend(self._check_succeeded_jobs(succeeded_jobs, claimed_osd_pvcs))

        if not issues:
            return RuleResult.passed()

        msg = "OSD prepare job issues detected:\n" + "\n".join(f"  - {i}" for i in issues)
        return RuleResult.failed(msg)

    def _check_exhausted_jobs(
        self, exhausted_jobs, claimed_osd_pvcs: set[str], pvc_phases: dict[str, str | None]
    ) -> list[str]:
        issues = []
        for job in exhausted_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            job_name = job.name()
            if pvc_name and pvc_name in claimed_osd_pvcs:
                continue  # Deployment creation shows preparation progressed, regardless of current OSD availability.
            pvc_info = self._format_pvc_info(pvc_name, pvc_phases)
            msg = (
                f"Job '{job_name}' failed after exhausting all retries{pvc_info} — OSD provisioning permanently failed."
            )
            termination_msgs = self._get_job_termination_messages_by_state_attr(job)
            if termination_msgs:
                msg += " Container exit messages: " + " | ".join(termination_msgs)
            issues.append(msg)
        return issues

    def _check_active_jobs(
        self, active_jobs, claimed_osd_pvcs: set[str], pvc_phases: dict[str, str | None]
    ) -> list[str]:
        """Report issues for jobs with active pods: missing PVC label, deleted PVC, or device already claimed."""
        issues = []
        for job in active_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            job_name = job.name()
            issue = None

            if not pvc_name:
                storage_type = self._get_job_storage_type(job)
                if storage_type == "host":
                    continue
                if storage_type == "pvc":
                    issue = f"Job '{job_name}' is missing its PVC mapping label."
                else:
                    issue = (
                        f"Cannot determine storage type for job '{job_name}'; "
                        "PVC-specific checks could not be performed."
                    )
            elif pvc_name in claimed_osd_pvcs:
                issue = (
                    f"Job '{job_name}' is active but PVC '{pvc_name}' "
                    "already has an OSD deployment — device is claimed."
                )
            elif pvc_phases.get(pvc_name) == self.PVC_NOT_FOUND:
                issue = (
                    f"Job '{job_name}' is active but PVC '{pvc_name}' was not found — the PVC may have been deleted."
                )
            elif pvc_name in pvc_phases and pvc_phases[pvc_name] == "Pending" and self._uses_local_storage({pvc_name}):
                pvc_obj = self.oc_api.select_single_resource(f"pvc/{pvc_name}", namespace=self.NAMESPACE)
                sc_name = getattr(pvc_obj.model.spec, "storageClassName", None) if pvc_obj else None
                if sc_name and not self._has_available_pv_for_pvc(sc_name):
                    issue = f"Job '{job.name()}' has PVC '{pvc_name}' in Pending phase; investigate PVC binding."
            if issue:
                termination_msgs = self._get_job_termination_messages_by_state_attr(job, "lastState")
                if termination_msgs:
                    issue += " Container exit messages: " + " | ".join(termination_msgs)
                issues.append(issue)
        return issues

    def _uses_local_storage(self, pvc_names: set[str]) -> bool:
        """Return True if any PVC in the set uses the local storage provisioner (kubernetes.io/no-provisioner)."""
        for pvc_name in pvc_names:
            pvc = self.oc_api.select_single_resource(f"pvc/{pvc_name}", namespace=self.NAMESPACE)
            if not pvc:
                continue
            storage_class_name = getattr(pvc.model.spec, "storageClassName", None)
            if not storage_class_name:
                continue
            sc = self.oc_api.select_single_resource(f"storageclass/{storage_class_name}")
            if sc and getattr(sc.model, "provisioner", None) == self.LOCAL_STORAGE_PROVISIONER:
                return True
        return False

    def _has_available_pv_for_pvc(self, storage_class_name: str) -> bool:
        """Return True if any Available PV exists for the given StorageClass."""
        return any(
            pv.model.status.phase == "Available" and pv.model.spec.storageClassName == storage_class_name
            for pv in self.oc_api.select_resources("pv")
        )

    def _get_job_storage_type(self, job) -> str:
        """Classify explicit PVC/host evidence, preserving missing or conflicting evidence as unknown."""
        spec = job.as_dict().get("spec", {}).get("template", {}).get("spec", {})
        labels = job.model.metadata.labels
        has_pvc_evidence = bool(labels.get(self.PVC_LABEL) or labels.get("ceph.rook.io/DeviceSet")) or any(
            volume.get("persistentVolumeClaim") for volume in spec.get("volumes") or []
        )
        containers = list(spec.get("containers") or []) + list(spec.get("initContainers") or [])
        pvc_markers = set()
        for container in containers:
            for env in container.get("env") or []:
                if env.get("name") == "ROOK_PVC_BACKED_OSD":
                    value = env.get("value")
                    pvc_markers.add(value if value in ("true", "false") and not env.get("valueFrom") else "unknown")

        if "false" in pvc_markers:
            if has_pvc_evidence or pvc_markers != {"false"}:
                return "unknown"
            return "host"
        if has_pvc_evidence or "true" in pvc_markers:
            return "pvc"
        return "unknown"

    def _get_prepare_jobs(self) -> list:
        return self.oc_api.select_resources(
            "job",
            namespace=self.NAMESPACE,
            labels={"app": "rook-ceph-osd-prepare"},
        )

    def _is_job_active(self, job) -> bool:
        return bool(getattr(job.model.status, "active", 0))

    def _get_claimed_osd_pvcs(self) -> set[str]:
        """Return PVC names that have an existing OSD deployment (device is claimed regardless of readiness)."""
        return {
            pvc
            for dep in self.oc_api.select_resources(
                "deployment",
                namespace=self.NAMESPACE,
                labels={"app": "rook-ceph-osd"},
            )
            if (pvc := dep.model.metadata.labels.get(self.PVC_LABEL))
        }

    def _is_job_failed(self, job) -> bool:
        conditions = getattr(job.model.status, "conditions", None) or []
        return any(getattr(c, "type", None) == "Failed" and getattr(c, "status", None) == "True" for c in conditions)

    def _is_job_succeeded(self, job) -> bool:
        return bool(getattr(job.model.status, "succeeded", 0))

    def _check_succeeded_jobs(self, succeeded_jobs, claimed_osd_pvcs: set[str]) -> list[str]:
        """Flag succeeded jobs with no OSD deployment for their PVC as confirmed device skips.

        A succeeded job may represent a Rook device skip (e.g. device already has a filesystem).
        The per-PVC status ConfigMap (rook-ceph-osd-<pvc>-status) determines whether the result
        is actionable:

        ConfigMap present, osds non-empty → Rook operator is mid-reconcile, will create the
            deployment; this is a transient race window and is silently skipped.
        ConfigMap present, osds empty     → pod ran and found nothing to deploy (confirmed skip).
        ConfigMap absent                  → operator processed the job, found no new OSDs, and
            deleted the ConfigMap (confirmed skip).

        Both confirmed-skip cases produce a failure. Container termination messages are appended
        as diagnostic context when available.
        Jobs whose PVC is already in `claimed_osd_pvcs` are skipped (OSD deployment exists).
        """
        issues = []
        for job in succeeded_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            if not pvc_name or pvc_name in claimed_osd_pvcs:
                continue
            if self._osd_status_configmap_pending(pvc_name):
                if not self._is_rook_operator_healthy():
                    issues.append(
                        f"Job '{job.name()}' completed but no OSD deployment found for PVC '{pvc_name}' "
                        "— Rook operator pod is not Running/Ready and cannot process the job."
                    )
                continue  # race window (operator healthy) or stalled (already flagged above)
            msg = (
                f"Job '{job.name()}' completed but no OSD deployment found for PVC '{pvc_name}' "
                "— check the OSD prepare pod logs to identify why the device was skipped."
            )
            termination_msgs = self._get_job_termination_messages_by_state_attr(job)
            if termination_msgs:
                msg += " Container exit messages: " + " | ".join(termination_msgs)
            issues.append(msg)
        return issues

    def _get_job_termination_messages_by_state_attr(self, job, state_attr: str = "state") -> list[str]:
        """Return terminated.message from every container of the job's pod(s).

        Args:
        job: Job resource object.
        state_attr: Container status attribute to read — ``"state"`` for
            finished pods (succeeded/exhausted jobs) or ``"lastState"`` for
            active pods whose previous attempt may have left a message.
        Returns:
            List of non-empty termination messages.
        """
        msgs = []
        pods = self.oc_api.get_pods(namespace=self.NAMESPACE, labels={"job-name": job.name()})
        for pod in pods:
            for cs in (pod.model.status.containerStatuses or []) + (pod.model.status.initContainerStatuses or []):
                terminated = getattr(getattr(cs, state_attr, None), "terminated", None)
                if terminated:
                    text = getattr(terminated, "message", None)
                    if text:
                        msgs.append(text.strip())
        return msgs

    def _get_pvc_phases(self, pvc_names: set[str]) -> dict[str, str | None]:
        """Return nullable PVC phases, using PVC_NOT_FOUND for missing PVCs."""
        result = {}
        for name in pvc_names:
            pvc = self.oc_api.select_single_resource(f"pvc/{name}", namespace=self.NAMESPACE)
            result[name] = pvc.model.status.phase if pvc else self.PVC_NOT_FOUND
        return result

    def _format_pvc_info(self, pvc_name: str, pvc_phases: dict[str, str | None]) -> str:
        if not pvc_name:
            return ""
        phase = pvc_phases.get(pvc_name)
        if phase == self.PVC_NOT_FOUND:
            return f" (PVC '{pvc_name}' not found in namespace)"
        if phase:
            return f" (PVC '{pvc_name}', phase: {phase})"
        return ""

    def _osd_status_configmap_pending(self, pvc_name: str) -> bool:
        """Return True if Rook has not yet finished processing this PVC's prepare job.

        The prepare pod writes the ConfigMap before exiting, so it is guaranteed to exist
        once the job reaches Succeeded. ConfigMap state determines the return value:

        - ConfigMap absent                  → False  (Rook deleted it after processing — confirmed skip)
        - status 'completed', osds present  → True   (Rook is about to create OSD deployments)
        - status 'completed', osds absent   → False  (Rook processed, nothing to deploy — confirmed skip)
        - Any other status                  → True   (conservative — anomalous for a Succeeded job)

        Args:
            pvc_name: Name of the PVC associated with the OSD prepare job.

        Returns:
            True if Rook may still create an OSD deployment (caller decides based on operator health).
            False if the device skip is confirmed (caller should report as failure).
        """
        cm_name = f"{self.OSD_STATUS_CONFIGMAP_PREFIX}{pvc_name}{self.OSD_STATUS_CONFIGMAP_SUFFIX}"
        cm = self.oc_api.select_single_resource(f"configmap/{cm_name}", namespace=self.NAMESPACE)
        if not cm:
            return False
        data = getattr(cm.model, "data", None) or {}
        cmd = f"oc get configmap/{cm_name} -n {self.NAMESPACE}"
        for value in data.values():
            parsed = parse_json(value, cmd=cmd, ip=self.get_host_ip())
            if isinstance(parsed, dict) and parsed.get("status") == "completed":
                return bool(parsed.get("osds"))
        return True  # ConfigMap exists but no 'completed' status yet — conservative, don't flag

    def _is_rook_operator_healthy(self) -> bool:
        """Return True if at least one rook-ceph-operator pod is Running with all containers ready."""
        return self.oc_api.is_any_pod_ready(self.NAMESPACE, {"app": "rook-ceph-operator"})


class OsdJournalError(InternalCephRule):
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

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result
        if not self._get_osd_pods():
            return PrerequisiteResult.not_met(f"No OSD pods found in {self.NAMESPACE} namespace.")
        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        osd_pods = self._get_osd_pods()
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
        return self.oc_api.get_pods(namespace=self.NAMESPACE, labels={"app": "rook-ceph-osd"})

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
        return_code, log_output, stderr = self.oc_api.run_oc_command(
            "logs",
            ["-n", self.NAMESPACE, pod_name, "--since=1h", "--tail=15"],
            timeout=30,
            raise_on_error=False,
        )

        if return_code != 0:
            log_output = f"<logs unavailable: {(stderr or '').strip()}>"

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
            if container.lastState and container.lastState.terminated:
                finished_at = container.lastState.terminated.finishedAt
                if finished_at:
                    try:
                        finished_time = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                        time_diff = (now - finished_time).total_seconds()
                        if 0 <= time_diff <= 3600:  # 1 hour = 3600 seconds
                            has_recent_restarts = True
                        elif time_diff < 0:
                            container_errors.append(
                                f"{container.name}: restart finishedAt '{finished_at}' is in the future "
                                "relative to the check clock; possible clock skew. "
                                "Restart recency cannot be determined."
                            )
                    except (ValueError, AttributeError):
                        pass

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
