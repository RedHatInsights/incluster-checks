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
       device (e.g. existing filesystem detected). terminationMessage is checked for the filesystem
       pattern to surface the specific cause.

    Reference: https://access.redhat.com/solutions/7057329
    """

    FILESYSTEM_ERROR_PATTERN = "because it contains a filesystem"

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
            if (n := job.model.metadata.labels.get("ceph.rook.io/pvc", ""))
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
            pvc_name = job.model.metadata.labels.get("ceph.rook.io/pvc", "")
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
            pvc_name = job.model.metadata.labels.get("ceph.rook.io/pvc", "")
            job_name = job.name()
            issue = None

            if not pvc_name:
                issue = f"Job '{job_name}' is active but has no 'ceph.rook.io/pvc' label — cannot determine device."
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
            if (pvc := dep.model.metadata.labels.get("ceph.rook.io/pvc"))
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
            pvc_name = job.model.metadata.labels.get("ceph.rook.io/pvc", "")
            if not pvc_name or pvc_name in running_osd_pvcs:
                continue
            msg = (
                f"Job '{job.name()}' completed but no OSD deployment found for PVC '{pvc_name}' "
                "— device may have been silently skipped."
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
        """Return {pvc_name: phase} for each PVC name, or None if not found."""
        result = {}
        for name in pvc_names:
            pvc = self.oc_api.select_single_resource(f"pvc/{name}", namespace=self.NAMESPACE)
            result[name] = pvc.model.status.phase if pvc else "not found"
        return result

    def _format_pvc_info(self, pvc_name: str, pvc_phases: dict[str, str | None]) -> str:
        if not pvc_name:
            return ""
        phase = pvc_phases.get(pvc_name)
        if phase == "not found":
            return f" (PVC '{pvc_name}' not found in namespace)"
        if phase:
            return f" (PVC '{pvc_name}', phase: {phase})"
        return ""


class OsdPrepareFilesystemHealth(InternalCephRule):
    """
    Check OSD prepare pods for active filesystem-related provisioning failures.

    Scans rook-ceph-osd-prepare pod logs for "existing filesystem" errors and correlates
    each pod to its OSD deployment to distinguish active failures from historical log noise.
    Replaces the disabled CCX rule that unconditionally recommended wipefs without checking
    whether provisioning had already recovered, risking data loss on healthy OSDs.

    Reference: https://access.redhat.com/solutions/6910101
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "osd_prepare_existing_filesystem"
    title = "Check OSD prepare pods for existing filesystem errors"
    links = [
        "https://access.redhat.com/solutions/6910101",
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/486836255",
    ]

    FILESYSTEM_ERROR_PATTERN = "because it contains a filesystem"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        base_result = super().is_prerequisite_fulfilled()
        if not base_result.fulfilled:
            return base_result

        prepare_pods = self._get_osd_prepare_pods()
        if not prepare_pods:
            return PrerequisiteResult.not_met("No rook-ceph-osd-prepare pods found in openshift-storage namespace.")

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        prepare_pods = self._get_osd_prepare_pods()
        pods_with_errors, unavailable_pods = self._check_prepare_pod_logs(prepare_pods)

        issues_msg = None
        down_osds_error: RuleResult | None = None
        unclassified_pods: list[str] = []
        osd_pvc_map = self._build_osd_pvc_map()
        if pods_with_errors:
            with_osd, without_osd = self._partition_pods_by_osd_correlation(pods_with_errors, osd_pvc_map)

            down_osd_prepare_pods_msg = None
            if with_osd:
                osd_tree = self._parse_osd_tree()
                if isinstance(osd_tree, RuleResult):
                    down_osds_error = osd_tree
                    unclassified_pods = [p["pod_name"] for p in with_osd]
                else:
                    down_osds, all_names = osd_tree
                    down_osd_prepare_pods_msg = self._check_down_osd_prepare_pods(with_osd, down_osds, all_names)

            failed_prepare_pods_msg = self._check_failed_prepare_pods(without_osd)
            parts = [m for m in [down_osd_prepare_pods_msg, failed_prepare_pods_msg] if m]
            if parts:
                issues_msg = "\n".join(parts)

        if issues_msg:
            msg = issues_msg
            if unclassified_pods:
                msg += (
                    f"\nNote: OSD tree data unavailable — {len(unclassified_pods)} correlated pod(s) "
                    f"could not be evaluated: {', '.join(unclassified_pods)}."
                )
            if unavailable_pods:
                msg += f"\nNote: Logs unavailable for {len(unavailable_pods)} pod(s): {', '.join(unavailable_pods)}."
            msg += (
                "\nRemediation: Investigate why OSD provisioning is failing. "
                "Before any cleanup, verify the affected device is not in use by an active OSD. "
                "See https://access.redhat.com/solutions/6910101"
            )
            return RuleResult.failed(msg)

        if down_osds_error is not None:
            return RuleResult.warning(
                f"Unable to evaluate {len(unclassified_pods)} OSD prepare pod(s) with filesystem errors "
                f"(ceph osd tree unavailable): {', '.join(unclassified_pods)}. "
                f"Verify OSD and prepare job status manually."
            )

        if unavailable_pods:
            return RuleResult.warning(
                f"Logs unavailable for {len(unavailable_pods)} OSD prepare pod(s): "
                f"{', '.join(unavailable_pods)} — unable to confirm absence of filesystem errors."
            )

        return RuleResult.passed()

    def _partition_pods_by_osd_correlation(
        self, pods_with_errors: list[dict], osd_pvc_map: dict[str, str]
    ) -> tuple[list[dict], list[dict]]:
        """Partition pods into those with a correlated OSD deployment and those without.

        For each pod, resolves its ``ceph.rook.io/pvc`` label to an OSD deployment and
        reads the ``ceph-osd-id`` label. Pods where a matching OSD deployment is found are
        enriched with an ``osd_id`` key; all others are uncorrelated.

        Returns:
            Tuple of (with_osd, without_osd) pod info lists.
        """
        with_osd = []
        without_osd = []
        for pod_info in pods_with_errors:
            pvc_name = pod_info.get("pvc_label")
            if pvc_name and pvc_name in osd_pvc_map:
                with_osd.append({**pod_info, "osd_id": osd_pvc_map[pvc_name]})
            else:
                without_osd.append(pod_info)
        return with_osd, without_osd

    def _check_failed_prepare_pods(self, pods_without_osd: list[dict]) -> str | None:
        """Check for active OSD prepare pods where no OSD deployment correlation was found.

        Fires for Running or Failed pods. Succeeded/Pending pods are skipped as historical or not yet started.

        Args:
            pods_without_osd: Pod info dicts for pods with no correlated OSD deployment

        Returns:
            Message string listing problematic pods, or None if none found
        """
        # Group by PVC to deduplicate retries; pods with no PVC label are keyed by pod name.
        by_pvc: dict[str, list[dict]] = {}
        for pod_info in pods_without_osd:
            if pod_info["phase"] not in ("Running", "Failed"):
                continue
            key = pod_info.get("pvc_label") or pod_info["pod_name"]
            by_pvc.setdefault(key, []).append(pod_info)

        if not by_pvc:
            return None

        msg = ""
        for group in by_pvc.values():
            representative = group[-1]
            phase = representative["phase"]
            pvc_label = representative.get("pvc_label")
            retry_suffix = f", retries: {len(group)}" if len(group) > 1 else ""
            if pvc_label:
                detail = f"(phase: {phase}{retry_suffix}) — no OSD deployment found for PVC '{pvc_label}'"
            else:
                detail = f"(phase: {phase}{retry_suffix}) — no ceph.rook.io/pvc label, device cannot be identified"
            msg += f"  - {representative['pod_name']} {detail}\n"
            msg += f"    Log: {representative['log_excerpt']}\n"

        return "OSD prepare pods with existing filesystem errors:\n" + msg

    def _check_down_osd_prepare_pods(
        self, pods_with_osd: list[dict], down_osds: list[str], all_osd_names: list[str]
    ) -> str | None:
        """Check pods with filesystem errors for correlated down OSDs or device-in-use conditions.

        Fires when:
        - The correlated OSD is down (provisioning failed, OSD lost).
        - The correlated OSD is absent from the Ceph tree — OSD deployment exists but never
          registered in Ceph, meaning provisioning stalled before the OSD could join.
        - The pod is Running while its OSD is already up (device in use by an active OSD).

        Pods whose correlated OSD is up and whose pod is not Running are skipped — the
        filesystem error was historical and provisioning recovered.

        Args:
            pods_with_osd: Pod info dicts enriched with an ``osd_id`` key
            down_osds: List of down OSD names from ceph osd tree
            all_osd_names: List of all OSD names present in ceph osd tree (any status)

        Returns:
            Message string if any pods match either condition, None otherwise
        """
        down_osds_set = set(down_osds)
        all_osd_names_set = set(all_osd_names)
        down_osd_lines = []
        in_use_lines = []

        for pod_info in pods_with_osd:
            osd_id = pod_info["osd_id"]
            if not osd_id:
                # Deployment claims the device but ceph-osd-id label is missing — can't look up OSD status
                if pod_info["phase"] == "Running":
                    in_use_lines.append(
                        f"  - {pod_info['pod_name']} (OSD deployment exists, Running — device may be in use)\n"
                        f"    Log: {pod_info['log_excerpt']}\n"
                    )
                continue
            osd_name = f"osd.{osd_id}"
            if osd_name in down_osds_set:
                down_osd_lines.append(
                    f"  - {pod_info['pod_name']} (phase: {pod_info['phase']}, correlated OSD: {osd_name})\n"
                    f"    Log: {pod_info['log_excerpt']}\n"
                )
            elif osd_name not in all_osd_names_set:
                down_osd_lines.append(
                    f"  - {pod_info['pod_name']} (phase: {pod_info['phase']}, correlated OSD: {osd_name}"
                    f" — not registered in Ceph tree, provisioning likely stalled)\n"
                    f"    Log: {pod_info['log_excerpt']}\n"
                )
            elif pod_info["phase"] == "Running":
                in_use_lines.append(
                    f"  - {pod_info['pod_name']} (correlated OSD: {osd_name} is up — device already in use)\n"
                    f"    Log: {pod_info['log_excerpt']}\n"
                )

        parts = []
        if down_osd_lines:
            parts.append(
                "OSD prepare pods with existing filesystem errors and correlated down OSDs:\n" + "".join(down_osd_lines)
            )
        if in_use_lines:
            parts.append(
                "Running OSD prepare pods with filesystem errors on devices already in use:\n" + "".join(in_use_lines)
            )

        return "\n".join(parts) if parts else None

    def _build_osd_pvc_map(self) -> dict[str, str]:
        """Return {pvc_name: osd_id} for all OSD deployments.

        osd_id is '' when the ceph-osd-id label is absent — the device is claimed but
        OSD status cannot be looked up by ID.
        """
        result = {}
        for dep in self.oc_api.select_resources(
            "deployment",
            namespace=self.NAMESPACE,
            labels={"app": "rook-ceph-osd"},
        ):
            pvc = dep.model.metadata.labels.get("ceph.rook.io/pvc")
            if pvc:
                result[pvc] = dep.model.metadata.labels.get("ceph-osd-id") or ""
        return result

    def _get_osd_prepare_pods(self) -> list:
        """Get all OSD prepare pods including completed ones."""
        return self.oc_api.get_pods(
            namespace=self.NAMESPACE,
            labels={"app": "rook-ceph-osd-prepare"},
        )

    def _check_prepare_pod_logs(self, pods: list) -> tuple[list[dict], list[str]]:
        """Collect filesystem signatures, current phases, and PVC labels from OSD prepare pod logs.

        Succeeded pods are skipped — they can never produce a finding regardless of log content.
        Fetches up to 10MB of logs from the last 24h and filters for FILESYSTEM_ERROR_PATTERN in Python.
        Pending pods with unavailable logs are silently skipped; non-Pending pods with
        unavailable logs are returned in the second element of the tuple so the caller
        can surface them in the result.

        Returns:
            Tuple of (pods_with_errors, unavailable_pod_names). pods_with_errors contains
            dicts with pod_name, phase, pvc_label, and log_excerpt. unavailable_pod_names
            lists non-Pending/non-Succeeded pods whose logs could not be fetched.
        """
        pods_with_errors = []
        unavailable_pods = []
        for pod in pods:
            if pod.model.status.phase == "Succeeded":
                continue
            pod_name = pod.name()
            rc, stdout, _ = self.oc_api.run_oc_command(
                "logs",
                [
                    "-n",
                    self.NAMESPACE,
                    pod_name,
                    "--all-containers",
                    "--since=24h",
                    f"--limit-bytes={10 * 1024 * 1024}",
                ],
                timeout=60,
                raise_on_error=False,
            )
            if rc != 0:
                if pod.model.status.phase not in ("Pending", None):
                    unavailable_pods.append(pod_name)
                continue

            error_lines = [line.strip() for line in stdout.splitlines() if self.FILESYSTEM_ERROR_PATTERN in line]
            if error_lines:
                pods_with_errors.append(
                    {
                        "pod_name": pod_name,
                        "phase": pod.model.status.phase,
                        "pvc_label": pod.model.metadata.labels.get("ceph.rook.io/pvc"),
                        "log_excerpt": "\n".join(error_lines[:5]),
                    }
                )

        return pods_with_errors, unavailable_pods


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
