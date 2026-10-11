"""
Tests for internal_ceph rules (InternalCephRule subclasses).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.rules.storage.internal_ceph import (
    OsdJournalError,
    OsdPrepareFilesystemHealth,
    OsdPrepareJobHealth,
)
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)

_REMEDIATION_MSG = (
    "\nRemediation: Investigate why OSD provisioning is failing. "
    "Before any cleanup, verify the affected device is not in use by an active OSD. "
    "See https://access.redhat.com/solutions/6910101"
)


def _make_job(
    name: str,
    active: int = 0,
    succeeded: int = 0,
    failed: int = 0,
    pvc: str = "",
    start_time: str | None = None,
    creation_timestamp: str | None = None,
    conditions: list | None = None,
) -> Mock:
    job = Mock()
    job.name.return_value = name
    job.model.status.active = active
    job.model.status.succeeded = succeeded
    job.model.status.failed = failed
    job.model.status.startTime = start_time
    job.model.status.conditions = conditions if conditions is not None else []
    job.model.metadata.labels = {"ceph.rook.io/pvc": pvc, "app": "rook-ceph-osd-prepare"}
    job.model.metadata.creationTimestamp = creation_timestamp
    return job


def _make_failed_condition() -> Mock:
    c = Mock()
    c.type = "Failed"
    c.status = "True"
    return c


def _make_osd_deployment(pvc: str) -> Mock:
    dep = Mock()
    dep.model.metadata.labels = {"app": "rook-ceph-osd", "ceph.rook.io/pvc": pvc}
    return dep


def _make_prepare_pod(pod_name: str, phase: str = "Succeeded", pvc: str = "ocs-deviceset-0-data-0abc") -> Mock:
    pod = Mock()
    pod.name.return_value = pod_name
    pod.model.status.phase = phase
    pod.model.metadata.labels = {"app": "rook-ceph-osd-prepare", "ceph.rook.io/pvc": pvc}
    return pod


def _make_pod_info(
    pod_name: str,
    phase: str = "Succeeded",
    pvc_label: str | None = "ocs-deviceset-0-data-0abc",
    log_excerpt: str = "skipping device /dev/sdb because it contains a filesystem",
) -> dict:
    return {
        "pod_name": pod_name,
        "phase": phase,
        "pvc_label": pvc_label,
        "log_excerpt": log_excerpt,
    }


class TestOsdPrepareJobHealth(RuleTestBase):
    """Test OsdPrepareJobHealth rule."""

    tested_type = OsdPrepareJobHealth

    _base_mocks = {
        "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
        "oc_api.select_single_resource": Mock(return_value=Mock()),
        "_is_external_ceph_mode": Mock(return_value=False),
        "_get_job_termination_messages": Mock(return_value=[]),
        "_get_job_last_termination_messages": Mock(return_value=[]),
    }

    scenario_passed = [
        RuleScenarioParams(
            "all prepare jobs complete with running OSDs — healthy",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-0abc"}),
            },
        ),
        RuleScenarioParams(
            "active job with OSD not yet up and PVC Bound — not a flaggable condition, rule passes",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-0",
                            active=1,
                            pvc="ocs-deviceset-0-data-0abc",
                            start_time=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-0abc": "Bound"}),
            },
        ),
        RuleScenarioParams(
            "exhausted job with running OSD — provisioning recovered, skip",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-9",
                            active=0,
                            pvc="ocs-deviceset-0-data-9vwx",
                            conditions=[_make_failed_condition()],
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-9vwx"}),
            },
        ),
        RuleScenarioParams(
            "job with no active pods and no Failed condition — not categorized, rule passes",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-o1",
                            active=0,
                            failed=0,
                            succeeded=0,
                            pvc="ocs-deviceset-0-data-o1abc",
                            start_time=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-o1abc"}),
            },
        ),
        RuleScenarioParams(
            "job with failed count but no Failed condition — not categorized as exhausted, rule passes",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-0",
                            active=0,
                            failed=2,
                            pvc="ocs-deviceset-0-data-0abc",
                            start_time=(datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-0abc": "Bound"}),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "active job for PVC that already has a running OSD",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", active=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-0abc"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' is active but PVC 'ocs-deviceset-0-data-0abc' "
                "already has a running OSD — device is in use."
            ),
        ),
        RuleScenarioParams(
            "active job with Pending PVC — no PV available",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-1", active=1, pvc="ocs-deviceset-0-data-1xyz"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-1xyz": "Pending"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-1' is stuck: PVC 'ocs-deviceset-0-data-1xyz' is Pending — "
                "no PV available."
            ),
        ),
        RuleScenarioParams(
            "active job with no PVC label — unlabelled job flagged",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-2", active=1, pvc=""),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-2' is active but has no 'ceph.rook.io/pvc' label — cannot determine device."
            ),
        ),
        RuleScenarioParams(
            "job exhausted backoffLimit — permanently failed, Bound PVC",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-8",
                            active=0,
                            pvc="ocs-deviceset-0-data-8stu",
                            conditions=[_make_failed_condition()],
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-8stu": "Bound"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-8' failed after exhausting all retries"
                " (PVC 'ocs-deviceset-0-data-8stu', phase: Bound) — OSD provisioning permanently failed."
            ),
        ),
        RuleScenarioParams(
            "job exhausted backoffLimit — PVC deleted (not found in namespace)",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-8b",
                            active=0,
                            pvc="ocs-deviceset-0-data-8del",
                            conditions=[_make_failed_condition()],
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-8del": "not found"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-8b' failed after exhausting all retries"
                " (PVC 'ocs-deviceset-0-data-8del' not found in namespace) — OSD provisioning permanently failed."
            ),
        ),
        RuleScenarioParams(
            "two exhausted jobs — one PVC found (Bound), one PVC deleted (not found in namespace)",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-8",
                            active=0,
                            pvc="ocs-deviceset-0-data-8stu",
                            conditions=[_make_failed_condition()],
                        ),
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-8b",
                            active=0,
                            pvc="ocs-deviceset-0-data-8del",
                            conditions=[_make_failed_condition()],
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(
                    return_value={
                        "ocs-deviceset-0-data-8stu": "Bound",
                        "ocs-deviceset-0-data-8del": "not found",
                    }
                ),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-8' failed after exhausting all retries"
                " (PVC 'ocs-deviceset-0-data-8stu', phase: Bound) — OSD provisioning permanently failed.\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-8b' failed after exhausting all retries"
                " (PVC 'ocs-deviceset-0-data-8del' not found in namespace) — OSD provisioning permanently failed."
            ),
        ),
        RuleScenarioParams(
            "succeeded job with no OSD deployment — device silently skipped",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_job_termination_messages": Mock(return_value=[]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' completed but no OSD deployment found for PVC 'ocs-deviceset-0-data-0abc'"
                " — device may have been silently skipped."
            ),
        ),
        RuleScenarioParams(
            "succeeded job with no OSD deployment — terminationMessage shows filesystem cause",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_job_termination_messages": Mock(
                    return_value=["skipping device /dev/sdb because it contains a filesystem"]
                ),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' completed but no OSD deployment found for PVC 'ocs-deviceset-0-data-0abc'"
                " — device may have been silently skipped."
                " Container exit messages: skipping device /dev/sdb because it contains a filesystem"
            ),
        ),
        RuleScenarioParams(
            "active job with Pending PVC and prior retry exit message",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-1", active=1, pvc="ocs-deviceset-0-data-1xyz"),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-1xyz": "Pending"}),
                "_get_job_last_termination_messages": Mock(return_value=["device /dev/sdb not found"]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-1' is stuck: PVC 'ocs-deviceset-0-data-1xyz' is Pending — "
                "no PV available."
                " Container exit messages: device /dev/sdb not found"
            ),
        ),
        RuleScenarioParams(
            "exhausted job with exit message from failed pod",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-8",
                            active=0,
                            pvc="ocs-deviceset-0-data-8stu",
                            conditions=[_make_failed_condition()],
                        ),
                    ]
                ),
                "_get_running_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-8stu": "Bound"}),
                "_get_job_termination_messages": Mock(return_value=["lvm2 error: device not found"]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-8' failed after exhausting all retries"
                " (PVC 'ocs-deviceset-0-data-8stu', phase: Bound) — OSD provisioning permanently failed."
                " Container exit messages: lvm2 error: device not found"
            ),
        ),
        RuleScenarioParams(
            "active job with non-ready OSD deployment — PVC claimed, flagged as device in use",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", active=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                # _get_running_osd_pvcs is NOT mocked — exercises the real implementation
                "oc_api.select_resources": Mock(return_value=[_make_osd_deployment("ocs-deviceset-0-data-0abc")]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' is active but PVC 'ocs-deviceset-0-data-0abc' "
                "already has a running OSD — device is in use."
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestOsdPrepareFilesystemHealth(RuleTestBase):
    """Test OsdPrepareFilesystemHealth rule."""

    tested_type = OsdPrepareFilesystemHealth

    _base_mocks = {
        "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
        "oc_api.select_single_resource": Mock(return_value=Mock()),
        "_is_external_ceph_mode": Mock(return_value=False),
        "_get_osd_prepare_pods": Mock(return_value=[Mock()]),
        "_parse_osd_tree": Mock(return_value=([], [])),
        "_build_osd_pvc_map": Mock(return_value={}),
    }

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no OSD prepare pods found",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_is_external_ceph_mode": Mock(return_value=False),
                "_get_osd_prepare_pods": Mock(return_value=[]),
            },
        ),
        RuleScenarioParams(
            "external Ceph mode",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_is_external_ceph_mode": Mock(return_value=True),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "no pods have filesystem errors in logs",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(return_value=([], [])),
            },
        ),
        RuleScenarioParams(
            "filesystem error in logs but correlated OSD is healthy — historical failure",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0")], [])
                ),
                "_parse_osd_tree": Mock(return_value=([], ["osd.0"])),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "0"}),
            },
        ),
        RuleScenarioParams(
            "filesystem error in logs, no PVC label, pod Succeeded — historical, skip",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Succeeded", pvc_label=None)], [])
                ),
                "_build_osd_pvc_map": Mock(return_value={}),
            },
        ),
        RuleScenarioParams(
            "Pending pod logs unavailable — skipped gracefully, rule passes",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_osd_prepare_pods": Mock(
                    return_value=[_make_prepare_pod("rook-ceph-osd-prepare-pvc-0", phase="Pending")]
                ),
                "oc_api.run_oc_command": Mock(return_value=(1, "", "container not created yet")),
            },
        ),
        RuleScenarioParams(
            "Succeeded pod — skipped before oc logs call, rule passes",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_osd_prepare_pods": Mock(
                    return_value=[_make_prepare_pod("rook-ceph-osd-prepare-pvc-0", phase="Succeeded")]
                ),
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "no errors found but non-Pending pod logs unavailable — warn",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(return_value=([], ["rook-ceph-osd-prepare-pvc-0"])),
            },
        ),
        RuleScenarioParams(
            "only with_osd pods and ceph osd tree fails — warn with pod names",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=(
                        [_make_pod_info("pod-with-osd", phase="Failed", pvc_label="ocs-deviceset-0-data-0abc")],
                        [],
                    )
                ),
                "_parse_osd_tree": Mock(return_value=RuleResult.failed("ceph osd tree command failed")),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "0"}),
            },
            failed_msg=(
                "Unable to evaluate 1 OSD prepare pod(s) with filesystem errors "
                "(ceph osd tree unavailable): pod-with-osd. "
                "Verify OSD and prepare job status manually."
            ),
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "Failed pod with filesystem error and correlated OSD down",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Failed", pvc_label="ocs-deviceset-0-data-0abc")], [])
                ),
                "_parse_osd_tree": Mock(return_value=(["osd.0"], ["osd.0"])),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "0"}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors and correlated down OSDs:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (phase: Failed, correlated OSD: osd.0)\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "filesystem error in Failed pod with no OSD correlation — fallback fires",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Failed", pvc_label=None)], [])
                ),
                "_build_osd_pvc_map": Mock(return_value={}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (phase: Failed) — no ceph.rook.io/pvc label, device cannot be identified\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "Running pod with filesystem error and OSD up — device in use",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Running", pvc_label="ocs-deviceset-0-data-0abc")], [])
                ),
                "_parse_osd_tree": Mock(return_value=([], ["osd.0"])),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "0"}),
            },
            failed_msg=(
                "Running OSD prepare pods with filesystem errors on devices already in use:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (correlated OSD: osd.0 is up — device already in use)\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "Running pod with filesystem error and no OSD correlation — active provisioning failure",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Running", pvc_label=None)], [])
                ),
                "_build_osd_pvc_map": Mock(return_value={}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (phase: Running) — no ceph.rook.io/pvc label, device cannot be identified\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "Running pod with filesystem error and OSD deployment missing ceph-osd-id label — fire as device in use",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Running", pvc_label="ocs-deviceset-0-data-0abc")], [])
                ),
                "_parse_osd_tree": Mock(return_value=([], [])),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": ""}),
            },
            failed_msg=(
                "Running OSD prepare pods with filesystem errors on devices already in use:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (OSD deployment exists, Running — device may be in use)\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "_parse_osd_tree fails — without_osd findings still reported",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=(
                        [
                            _make_pod_info("pod-with-osd", phase="Failed", pvc_label="ocs-deviceset-0-data-0abc"),
                            _make_pod_info("pod-without-osd", phase="Failed", pvc_label=None),
                        ],
                        [],
                    )
                ),
                "_parse_osd_tree": Mock(return_value=RuleResult.failed("ceph osd tree command failed")),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "0"}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors:\n"
                "  - pod-without-osd (phase: Failed) — no ceph.rook.io/pvc label, device cannot be identified\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                "\nNote: OSD tree data unavailable — 1 correlated pod(s) could not be evaluated: pod-with-osd."
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "Failed pod with PVC label but no OSD deployment — deployment may have been deleted",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=(
                        [_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Failed", pvc_label="ocs-deviceset-0-data-0abc")],
                        [],
                    )
                ),
                "_build_osd_pvc_map": Mock(return_value={}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (phase: Failed) — no OSD deployment found for PVC 'ocs-deviceset-0-data-0abc'\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
        RuleScenarioParams(
            "Failed pod with OSD deployment but OSD never registered in Ceph tree",
            tested_object_mock_dict={
                **_base_mocks,
                "_check_prepare_pod_logs": Mock(
                    return_value=([_make_pod_info("rook-ceph-osd-prepare-pvc-0", phase="Failed", pvc_label="ocs-deviceset-0-data-0abc")], [])
                ),
                "_parse_osd_tree": Mock(return_value=([], [])),
                "_build_osd_pvc_map": Mock(return_value={"ocs-deviceset-0-data-0abc": "5"}),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors and correlated down OSDs:\n"
                "  - rook-ceph-osd-prepare-pvc-0 (phase: Failed, correlated OSD: osd.5"
                " — not registered in Ceph tree, provisioning likely stalled)\n"
                "    Log: skipping device /dev/sdb because it contains a filesystem\n"
                + _REMEDIATION_MSG
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


def create_pod_mock(
    name, phase="Running", ready=True, restarts=0, last_restart=None, waiting_reason=None, terminated_reason=None
):
    """Create a mock pod object for testing."""
    mock_pod = Mock()

    container_state = Mock()
    container_state.running = Mock() if phase == "Running" and not waiting_reason and not terminated_reason else None
    container_state.waiting = Mock(reason=waiting_reason, message="") if waiting_reason else None
    container_state.terminated = Mock(reason=terminated_reason, message="") if terminated_reason else None

    container_status = Mock()
    container_status.name = name
    container_status.ready = ready
    container_status.restartCount = restarts
    container_status.state = container_state

    if last_restart:
        last_state = Mock()
        last_state.terminated = Mock(finishedAt=last_restart)
        container_status.lastState = last_state
    else:
        container_status.lastState = Mock(terminated=None)

    mock_pod.model.status.phase = phase
    mock_pod.model.status.containerStatuses = [container_status]
    mock_pod.model.metadata.labels = {"ceph-osd-id": name.split("-")[-1]} if "osd" in name else {}
    mock_pod.name.return_value = name

    return mock_pod


class TestOsdJournalError(RuleTestBase):
    """Test OsdJournalError rule."""

    tested_type = OsdJournalError

    scenario_passed = [
        RuleScenarioParams(
            "all OSD pods healthy",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Running", ready=True, restarts=0),
                        create_pod_mock("rook-ceph-osd-1", phase="Running", ready=True, restarts=0),
                    ]
                ),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "OSD pod not running",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Pending", ready=False, restarts=0),
                    ]
                ),
                "oc_api.run_oc_command": Mock(return_value=(0, "pod logs here", "")),
            },
            failed_msg=(
                "Pod Name: rook-ceph-osd-0\n"
                "OSD ID: 0\n"
                "Status: Pending\n"
                "Recent Logs (last 15 lines or 1 hour):\n"
                "pod logs here\n"
            ),
        ),
        RuleScenarioParams(
            "OSD pod with recent restarts",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock(
                            "rook-ceph-osd-0",
                            phase="Running",
                            ready=True,
                            restarts=5,
                            last_restart=datetime.now(timezone.utc).isoformat(),
                        ),
                    ]
                ),
                "oc_api.run_oc_command": Mock(return_value=(0, "pod logs here", "")),
            },
            failed_msg=(
                "Pod Name: rook-ceph-osd-0\n"
                "OSD ID: 0\n"
                "Status: Running\n"
                "Recent Logs (last 15 lines or 1 hour):\n"
                "pod logs here\n"
            ),
        ),
        RuleScenarioParams(
            "OSD pod in CrashLoopBackOff",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Running", ready=False, waiting_reason="CrashLoopBackOff"),
                    ]
                ),
                "oc_api.run_oc_command": Mock(return_value=(0, "pod logs here", "")),
            },
            failed_msg=(
                "Pod Name: rook-ceph-osd-0\n"
                "OSD ID: 0\n"
                "Status: Running\n"
                "Container Errors:\n"
                "  - rook-ceph-osd-0: CrashLoopBackOff - \n"
                "Recent Logs (last 15 lines or 1 hour):\n"
                "pod logs here\n"
            ),
        ),
        RuleScenarioParams(
            "OSD pod not running and oc logs fails — logs unavailable shown in error",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Pending", ready=False, restarts=0),
                    ]
                ),
                "oc_api.run_oc_command": Mock(return_value=(1, "", "container not created yet")),
            },
            failed_msg=(
                "Pod Name: rook-ceph-osd-0\n"
                "OSD ID: 0\n"
                "Status: Pending\n"
                "Recent Logs (last 15 lines or 1 hour):\n"
                "<logs unavailable: container not created yet>\n"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
