import re
from datetime import datetime, timezone

from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.rules.storage.storage_validations import CephRule
from in_cluster_checks.utils.enums import Objectives


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
    1. Job has no 'ceph.rook.io/pvc' label — device cannot be identified.
    2. Job's PVC already has a running OSD deployment — device is in use.
    3. Job's PVC is Pending — no PV available (more PVCs configured than PVs exist).

    Exhausted jobs (status.conditions contains Failed=True, no active pods) are flagged when:
    4. Job exhausted its backoffLimit with no running OSD — OSD provisioning permanently failed.
       Skipped if a running OSD deployment exists for the PVC (provisioning recovered).

    Succeeded jobs (status.succeeded > 0) are flagged when:
    5. Job completed cleanly but no OSD deployment exists for its PVC — Rook silently skipped the
       device. Container termination messages are included as diagnostic context when available.

    Reference: https://access.redhat.com/solutions/7057329
    """

    PVC_LABEL = "ceph.rook.io/pvc"
    PVC_NOT_FOUND = "not found"

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
        running_osd_pvcs: set[str] = set()
        pvc_phases: dict[str, str | None] = {}
        if all_pvc_names:
            running_osd_pvcs = self._get_running_osd_pvcs()
            pvc_names_to_check = all_pvc_names - running_osd_pvcs
            pvc_phases = self._get_pvc_phases(pvc_names_to_check) if pvc_names_to_check else {}

        issues = []

        issues.extend(self._check_active_jobs(active_jobs, running_osd_pvcs, pvc_phases))
        issues.extend(self._check_exhausted_jobs(exhausted_jobs, running_osd_pvcs, pvc_phases))
        issues.extend(self._check_succeeded_jobs(succeeded_jobs, running_osd_pvcs))

        if not issues:
            return RuleResult.passed()

        msg = "OSD prepare job issues detected:\n" + "\n".join(f"  - {i}" for i in issues)
        return RuleResult.failed(msg)

    def _check_exhausted_jobs(
        self, exhausted_jobs, running_osd_pvcs: set[str], pvc_phases: dict[str, str | None]
    ) -> list[str]:
        issues = []
        for job in exhausted_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            job_name = job.name()
            if pvc_name and pvc_name in running_osd_pvcs:
                continue  # OSD is running — provisioning recovered despite job failure
            pvc_info = self._format_pvc_info(pvc_name, pvc_phases)
            msg = (
                f"Job '{job_name}' failed after exhausting all retries{pvc_info} — OSD provisioning permanently failed."
            )
            termination_msgs = self._get_job_termination_messages(job)
            if termination_msgs:
                msg += " Container exit messages: " + " | ".join(termination_msgs)
            issues.append(msg)
        return issues

    def _check_active_jobs(
        self, active_jobs, running_osd_pvcs: set[str], pvc_phases: dict[str, str | None]
    ) -> list[str]:
        """Report issues for jobs with active pods: missing PVC label, OSD already running, or PVC stuck Pending."""
        issues = []
        for job in active_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            job_name = job.name()
            issue = None

            if not pvc_name:
                issue = f"Job '{job_name}' is active but has no '{self.PVC_LABEL}' label — cannot determine device."
            elif pvc_name in running_osd_pvcs:
                issue = f"Job '{job_name}' is active but PVC '{pvc_name}' already has a running OSD — device is in use."
            elif pvc_name in pvc_phases and pvc_phases[pvc_name] == "Pending":
                issue = f"Job '{job_name}' is stuck: PVC '{pvc_name}' is Pending — no PV available."

            if issue:
                termination_msgs = self._get_job_last_termination_messages(job)
                if termination_msgs:
                    issue += " Container exit messages: " + " | ".join(termination_msgs)
                issues.append(issue)
        return issues

    def _get_prepare_jobs(self) -> list:
        return self.oc_api.select_resources(
            "job",
            namespace=self.NAMESPACE,
            labels={"app": "rook-ceph-osd-prepare"},
        )

    def _is_job_active(self, job) -> bool:
        return bool(getattr(job.model.status, "active", 0))

    def _get_running_osd_pvcs(self) -> set[str]:
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

    def _check_succeeded_jobs(self, succeeded_jobs, running_osd_pvcs: set[str]) -> list[str]:
        """Flag succeeded jobs where no OSD deployment was created for their PVC.

        A job can complete cleanly (exit 0) while Rook silently skips the device — for example,
        when the device already has a filesystem. terminationMessage from all containers is
        included as diagnostic context when available.
        """
        issues = []
        for job in succeeded_jobs:
            pvc_name = job.model.metadata.labels.get(self.PVC_LABEL, "")
            if not pvc_name or pvc_name in running_osd_pvcs:
                continue
            msg = (
                f"Job '{job.name()}' completed but no OSD deployment found for PVC '{pvc_name}' "
                "— check the OSD prepare pod logs to identify why the device was skipped."
            )
            termination_msgs = self._get_job_termination_messages(job)
            if termination_msgs:
                msg += " Container exit messages: " + " | ".join(termination_msgs)
            issues.append(msg)
        return issues

    def _get_job_termination_messages(self, job) -> list[str]:
        """Return state.terminated.message from every container of the job's pod(s).

        For succeeded/exhausted jobs — pods are done, state.terminated holds the exit message.
        """
        msgs = []
        pods = self.oc_api.get_pods(namespace=self.NAMESPACE, labels={"job-name": job.name()})
        for pod in pods:
            for cs in pod.model.status.containerStatuses or []:
                terminated = getattr(getattr(cs, "state", None), "terminated", None)
                if terminated:
                    text = getattr(terminated, "message", None)
                    if text:
                        msgs.append(text.strip())
        return msgs

    def _get_job_last_termination_messages(self, job) -> list[str]:
        """Return lastState.terminated.message from every container of the job's pod(s).

        For active jobs — the current pod is running (state.terminated is None), but prior
        failed attempts may have left messages in lastState.terminated.
        """
        msgs = []
        pods = self.oc_api.get_pods(namespace=self.NAMESPACE, labels={"job-name": job.name()})
        for pod in pods:
            for cs in pod.model.status.containerStatuses or []:
                terminated = getattr(getattr(cs, "lastState", None), "terminated", None)
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
                        if time_diff <= 3600:  # 1 hour = 3600 seconds
                            has_recent_restarts = True
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
