"""
Tests for internal_ceph rules (InternalCephRule subclasses).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.storage.internal_ceph import (
    OsdJournalError,
    OsdPrepareJobHealth,
)
from in_cluster_checks.utils.enums import Status
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)

HOST_DEVICE_POD_SPEC = {
    "volumes": [{"name": "rootfs", "hostPath": {"path": "/"}}],
    "containers": [
        {
            "name": "provision",
            "volumeMounts": [{"name": "rootfs", "mountPath": "/rootfs"}],
            "env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "false"}],
        }
    ],
}


def _make_job(
    name: str,
    active: int = 0,
    succeeded: int = 0,
    failed: int = 0,
    pvc: str = "",
    start_time: str | None = None,
    creation_timestamp: str | None = None,
    conditions: list | None = None,
    pod_spec: dict | None = None,
) -> Mock:
    job = Mock()
    job.name.return_value = name
    job.model.status.active = active
    job.model.status.succeeded = succeeded
    job.model.status.failed = failed
    job.model.status.startTime = start_time
    job.model.status.conditions = conditions if conditions is not None else []
    job.model.metadata.labels = {"app": "rook-ceph-osd-prepare"}
    if pvc:
        job.model.metadata.labels["ceph.rook.io/pvc"] = pvc
    job.model.metadata.creationTimestamp = creation_timestamp
    job.as_dict.return_value = {"spec": {"template": {"spec": pod_spec or {}}}}
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


class TestOsdPrepareJobHealth(RuleTestBase):
    """Test OsdPrepareJobHealth rule."""

    tested_type = OsdPrepareJobHealth

    _base_mocks = {
        "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
        "oc_api.select_single_resource": Mock(return_value=Mock()),
        "_is_external_ceph_mode": Mock(return_value=False),
        "_get_job_termination_messages_by_state_attr": Mock(return_value=[]),
        "_osd_status_configmap_pending": Mock(return_value=False),
    }

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "external Ceph mode",
            tested_object_mock_dict={
                **_base_mocks,
                "_is_external_ceph_mode": Mock(return_value=True),
            },
        ),
        RuleScenarioParams(
            "no OSD prepare jobs",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(return_value=[]),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "active host-device job without PVC label — no preparation failure established",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-node-1", active=1, pod_spec=HOST_DEVICE_POD_SPEC),
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "all prepare jobs complete with running OSDs — healthy",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-0abc"}),
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-0abc": "Bound"}),
            },
        ),
        RuleScenarioParams(
            "exhausted job with OSD deployment — preparation progressed, skip",
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
                "_get_claimed_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-9vwx"}),
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
                "_get_claimed_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-o1abc"}),
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-0abc": "Bound"}),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "active job has no explicit storage type",
            tested_object_mock_dict={
                "_get_prepare_jobs": Mock(return_value=[_make_job("prepare-unknown", active=1)]),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=[]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Cannot determine storage type for job 'prepare-unknown'; "
                "PVC-specific checks could not be performed."
            ),
        ),
        *[
            RuleScenarioParams(
                title,
                tested_object_mock_dict={
                    "_get_job_termination_messages_by_state_attr": Mock(return_value=[]),
                    "_get_prepare_jobs": Mock(return_value=[_make_job("prepare-pvc", active=1, pod_spec=pod_spec)]),
                },
                failed_msg=(
                    "OSD prepare job issues detected:\n" "  - Job 'prepare-pvc' is missing its PVC mapping label."
                ),
            )
            for title, pod_spec in [
                (
                    "PVC volume establishes missing mapping",
                    {"volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "osd-data"}}]},
                ),
                (
                    "PVC marker establishes missing mapping",
                    {"containers": [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "true"}]}]},
                ),
            ]
        ],
        RuleScenarioParams(
            "active job for PVC that already has an OSD deployment",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", active=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-0abc"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' is active but PVC 'ocs-deviceset-0-data-0abc' "
                "already has an OSD deployment — device is claimed."
            ),
        ),
        RuleScenarioParams(
            "active job whose PVC was deleted",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-del", active=1, pvc="ocs-deviceset-0-data-9del"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-9del": "not found"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-del' is active but PVC 'ocs-deviceset-0-data-9del' "
                "was not found — the PVC may have been deleted."
            ),
        ),
        RuleScenarioParams(
            "host-device job without PVC label exhausted retries — explicit failure still reported",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-node-1",
                            conditions=[_make_failed_condition()],
                            pod_spec=HOST_DEVICE_POD_SPEC,
                        ),
                    ]
                ),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-node-1' failed after exhausting all retries"
                " — OSD provisioning permanently failed."
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=[]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' completed but no OSD deployment found for PVC 'ocs-deviceset-0-data-0abc'"
                " — check the OSD prepare pod logs to identify why the device was skipped."
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_job_termination_messages_by_state_attr": Mock(
                    return_value=["skipping device /dev/sdb because it contains a filesystem"]
                ),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' completed but no OSD deployment found for PVC 'ocs-deviceset-0-data-0abc'"
                " — check the OSD prepare pod logs to identify why the device was skipped."
                " Container exit messages: skipping device /dev/sdb because it contains a filesystem"
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
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-8stu": "Bound"}),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=["lvm2 error: device not found"]),
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
                # _get_claimed_osd_pvcs is NOT mocked — exercises the real implementation
                "oc_api.select_resources": Mock(return_value=[_make_osd_deployment("ocs-deviceset-0-data-0abc")]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' is active but PVC 'ocs-deviceset-0-data-0abc' "
                "already has an OSD deployment — device is claimed."
            ),
        ),
    ]

    scenario_failed = scenario_failed + [
        RuleScenarioParams(
            "active job with Pending PVC and no available local PV",
            tested_object_mock_dict={
                **_base_mocks,
                "_uses_local_storage": Mock(return_value=True),
                "_has_available_pv_for_pvc": Mock(return_value=False),
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-1",
                            active=1,
                            pvc="ocs-deviceset-0-data-1xyz",
                            creation_timestamp="2020-01-01T00:00:00Z",
                        ),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-1xyz": "Pending"}),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-1' has PVC 'ocs-deviceset-0-data-1xyz' "
                "in Pending phase; investigate PVC binding."
            ),
        ),
        RuleScenarioParams(
            "succeeded job, ConfigMap present with osds but Rook operator stalled — reported as failure",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_osd_status_configmap_pending": Mock(return_value=True),
                "_is_rook_operator_healthy": Mock(return_value=False),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-0' completed but no OSD deployment found for PVC "
                "'ocs-deviceset-0-data-0abc' — Rook operator pod is not Running/Ready and cannot process the job."
            ),
        ),
        RuleScenarioParams(
            "active job with Pending PVC, no available local PV, prior retry exit message",
            tested_object_mock_dict={
                **_base_mocks,
                "_uses_local_storage": Mock(return_value=True),
                "_has_available_pv_for_pvc": Mock(return_value=False),
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job(
                            "rook-ceph-osd-prepare-pvc-1",
                            active=1,
                            pvc="ocs-deviceset-0-data-1xyz",
                            creation_timestamp="2020-01-01T00:00:00Z",
                        ),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-1xyz": "Pending"}),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=["device /dev/sdb not found"]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Job 'rook-ceph-osd-prepare-pvc-1' has PVC 'ocs-deviceset-0-data-1xyz' "
                "in Pending phase; investigate PVC binding."
                " Container exit messages: device /dev/sdb not found"
            ),
        ),
    ]

    scenario_passed = scenario_passed + [
        RuleScenarioParams(
            "succeeded job, ConfigMap present with osds — genuine race window, silently skipped",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_osd_status_configmap_pending": Mock(return_value=True),
                "_is_rook_operator_healthy": Mock(return_value=True),
            },
        ),
        RuleScenarioParams(
            "succeeded job, Rook operator stalled but PVC already claimed — not flagged",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("rook-ceph-osd-prepare-pvc-0", succeeded=1, pvc="ocs-deviceset-0-data-0abc"),
                    ]
                ),
                "_get_claimed_osd_pvcs": Mock(return_value={"ocs-deviceset-0-data-0abc"}),
                "_is_rook_operator_healthy": Mock(return_value=False),
            },
        ),
        RuleScenarioParams(
            "active job with Pending PVC but available PV exists — binding pending, not flagged",
            tested_object_mock_dict={
                **_base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[_make_job("prepare-data", active=1, pvc="ocs-deviceset-0-data-0abc")]
                ),
                "_uses_local_storage": Mock(return_value=True),
                "_has_available_pv_for_pvc": Mock(return_value=True),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"ocs-deviceset-0-data-0abc": "Pending"}),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize(
        "cm_data, expected",
        [
            # status=completed + osds non-empty → genuine race window
            ({"status": '{"status": "completed", "osds": [{"id": 0}]}'}, True),
            # status=completed + osds empty → confirmed skip (pod skipped device)
            ({"status": '{"status": "completed", "osds": []}'}, False),
            # status=completed + no osds key → confirmed skip
            ({"status": '{"status": "completed"}'}, False),
            # other statuses → conservative True (pod still running, anomalous for Succeeded job)
            ({"status": '{"status": "orchestrating"}'}, True),
            ({"status": '{"status": "starting"}'}, True),
            ({}, True),
        ],
    )
    def test_osd_status_configmap_pending(self, cm_data, expected, tested_object):
        cm = Mock()
        cm.model.data = cm_data
        tested_object.oc_api.select_single_resource = Mock(return_value=cm)
        assert tested_object._osd_status_configmap_pending("ocs-deviceset-0-data-0abc") is expected
        tested_object.oc_api.select_single_resource.assert_called_once_with(
            "configmap/rook-ceph-osd-ocs-deviceset-0-data-0abc-status",
            namespace=tested_object.NAMESPACE,
        )

    def test_osd_status_configmap_absent_means_rook_processed(self, tested_object):
        tested_object.oc_api.select_single_resource = Mock(return_value=None)
        assert tested_object._osd_status_configmap_pending("ocs-deviceset-0-data-0abc") is False

    @pytest.mark.parametrize("desired_replicas", [0, 1])
    def test_exhausted_job_with_unavailable_osd_deployment(self, desired_replicas, tested_object):
        deployment = _make_osd_deployment("osd-data")
        deployment.model.spec.replicas = desired_replicas
        deployment.model.status.availableReplicas = 0
        scenario = RuleScenarioParams(
            "historical failed prepare job with unavailable OSD deployment",
            tested_object_mock_dict={
                **self._base_mocks,
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("prepare-data", pvc="osd-data", conditions=[_make_failed_condition()]),
                    ]
                ),
                "oc_api.select_resources": Mock(return_value=[deployment]),
            },
        )
        RuleTestBase.test_scenario_passed(self, scenario, tested_object)

    @pytest.mark.parametrize(
        "labels, volumes, containers, init_containers, expected",
        [
            ({"ceph.rook.io/pvc": "data"}, [], [], [], "pvc"),
            ({"ceph.rook.io/DeviceSet": "set-1"}, [], [], [], "pvc"),
            ({}, [{"persistentVolumeClaim": {"claimName": "data"}}], [], [], "pvc"),
            ({}, [], [], [], "unknown"),
            ({}, [], [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "true"}]}], [], "pvc"),
            ({}, [], [], [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "true"}]}], "pvc"),
            ({}, [], [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "false"}]}], [], "host"),
            (
                {"ceph.rook.io/DeviceSet": "set-1"},
                [],
                [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "false"}]}],
                [],
                "unknown",
            ),
            (
                {},
                [],
                [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "false"}]}],
                [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "true"}]}],
                "unknown",
            ),
            (
                {},
                [],
                [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "value": "false"}]}],
                [{"env": [{"name": "ROOK_PVC_BACKED_OSD", "valueFrom": {"fieldRef": {}}}]}],
                "unknown",
            ),
        ],
    )
    def test_storage_type(self, labels, volumes, containers, init_containers, expected, tested_object):
        job = _make_job(
            "prepare", pod_spec={"volumes": volumes, "containers": containers, "initContainers": init_containers}
        )
        job.model.metadata.labels.update(labels)
        assert tested_object._get_job_storage_type(job) == expected

    def test_failure_includes_unknown_storage(self, tested_object):
        scenario = RuleScenarioParams(
            "exhausted host job and unknown active job",
            tested_object_mock_dict={
                "_get_prepare_jobs": Mock(
                    return_value=[
                        _make_job("prepare-host", conditions=[_make_failed_condition()], pod_spec=HOST_DEVICE_POD_SPEC),
                        _make_job("prepare-unknown", active=1),
                    ]
                ),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=[]),
            },
            failed_msg=(
                "OSD prepare job issues detected:\n"
                "  - Cannot determine storage type for job 'prepare-unknown'; PVC-specific checks could not be performed.\n"
                "  - Job 'prepare-host' failed after exhausting all retries — OSD provisioning permanently failed."
            ),
        )
        RuleTestBase.test_scenario_failed(self, scenario, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize(
        "timestamp", ["2020-01-01T00:00:00Z", datetime.now(timezone.utc).isoformat(), None, "invalid"]
    )
    def test_pending_pvc_fails_regardless_of_job_age(self, timestamp, tested_object):
        job = _make_job("prepare", active=1, pvc="data", creation_timestamp=timestamp)
        scenario = RuleScenarioParams(
            "Pending PVC fails regardless of job age on local storage with no available PV",
            tested_object_mock_dict={
                **self._base_mocks,
                "_uses_local_storage": Mock(return_value=True),
                "_has_available_pv_for_pvc": Mock(return_value=False),
                "_get_prepare_jobs": Mock(return_value=[job]),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"data": "Pending"}),
                "_get_job_termination_messages_by_state_attr": Mock(return_value=["retry diagnostic"]),
            },
        )
        self._init_validation_object(tested_object, scenario)
        with self._apply_patches(scenario, tested_object):
            result = tested_object.run_rule()
        assert result.status == Status.FAILED
        assert result.message == (
            "OSD prepare job issues detected:\n"
            "  - Job 'prepare' has PVC 'data' in Pending phase; investigate PVC binding."
            " Container exit messages: retry diagnostic"
        )

    def test_uses_local_storage_provisioner_check(self, tested_object):
        """_uses_local_storage returns True only for kubernetes.io/no-provisioner."""
        pvc_mock = Mock()
        pvc_mock.model.spec.storageClassName = "localblock"
        sc_local = Mock()
        sc_local.model.provisioner = "kubernetes.io/no-provisioner"
        sc_dynamic = Mock()
        sc_dynamic.model.provisioner = "ebs.csi.aws.com"

        tested_object.oc_api.select_single_resource = Mock(side_effect=[pvc_mock, sc_local])
        assert tested_object._uses_local_storage({"ocs-deviceset-0-data-0abc"}) is True

        tested_object.oc_api.select_single_resource = Mock(side_effect=[pvc_mock, sc_dynamic])
        assert tested_object._uses_local_storage({"ocs-deviceset-0-data-0abc"}) is False

    def test_uses_local_storage_no_pvc_found(self, tested_object):
        tested_object.oc_api.select_single_resource = Mock(return_value=None)
        assert tested_object._uses_local_storage({"missing-pvc"}) is False

    @pytest.mark.parametrize(
        "pv_specs, expected",
        [
            ([], False),
            ([("Available", "localblock")], True),
            ([("Bound", "localblock")], False),
            ([("Available", "other-storage")], False),
            ([("Bound", "localblock"), ("Available", "localblock")], True),
        ],
    )
    def test_has_available_pv_for_pvc(self, pv_specs, expected, tested_object):
        pvs = []
        for phase, storage_class in pv_specs:
            pv = Mock()
            pv.model.status.phase = phase
            pv.model.spec.storageClassName = storage_class
            pvs.append(pv)
        tested_object.oc_api.select_resources = Mock(return_value=pvs)

        assert tested_object._has_available_pv_for_pvc("localblock") is expected
        tested_object.oc_api.select_resources.assert_called_once_with("pv")

    @pytest.mark.parametrize("local_storage", [False, True])
    @pytest.mark.parametrize("exhausted_job", [False, True])
    def test_pending_pvc_with_other_job_failures(self, local_storage, exhausted_job, tested_object):
        jobs = [_make_job("prepare-pending", active=1, pvc="pending-data")]
        if exhausted_job:
            jobs.append(_make_job("prepare-failed", pvc="failed-data", conditions=[_make_failed_condition()]))
        scenario = RuleScenarioParams(
            "Pending PVC and exhausted job severity",
            tested_object_mock_dict={
                **self._base_mocks,
                "_get_prepare_jobs": Mock(return_value=jobs),
                "_get_claimed_osd_pvcs": Mock(return_value=set()),
                "_get_pvc_phases": Mock(return_value={"pending-data": "Pending", "failed-data": "Bound"}),
                "_uses_local_storage": Mock(return_value=local_storage),
                "_has_available_pv_for_pvc": Mock(return_value=False),
            },
        )
        self._init_validation_object(tested_object, scenario)
        with self._apply_patches(scenario, tested_object):
            assert tested_object.is_prerequisite_fulfilled().fulfilled
            result = tested_object.run_rule()
        expected_status = Status.FAILED if exhausted_job or local_storage else Status.PASSED
        assert result.status == expected_status
        if exhausted_job:
            assert "Job 'prepare-failed' failed after exhausting all retries" in result.message
        if local_storage:
            assert "Job 'prepare-pending' has PVC 'pending-data' in Pending phase" in result.message
        elif result.message:
            assert "in Pending phase" not in result.message


def _create_pod_with_untimed_restart(name, restarts=1):
    """Create a Running/ready pod mock where lastState.terminated exists but finishedAt is None."""
    mock_pod = Mock()

    container_state = Mock()
    container_state.running = Mock()
    container_state.waiting = None
    container_state.terminated = None

    last_state = Mock()
    last_state.terminated = Mock(finishedAt=None)

    container_status = Mock()
    container_status.name = name
    container_status.ready = True
    container_status.restartCount = restarts
    container_status.state = container_state
    container_status.lastState = last_state

    mock_pod.model.status.phase = "Running"
    mock_pod.model.status.containerStatuses = [container_status]
    mock_pod.model.metadata.labels = {"ceph-osd-id": name.split("-")[-1]} if "osd" in name else {}
    mock_pod.name.return_value = name

    return mock_pod


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

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "external Ceph mode",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_is_external_ceph_mode": Mock(return_value=True),
            },
        ),
        RuleScenarioParams(
            "no OSD pods",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_is_external_ceph_mode": Mock(return_value=False),
                "_get_osd_pods": Mock(return_value=[]),
            },
        ),
    ]

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
        ),
        RuleScenarioParams(
            "OSD pod restarted but no termination timestamp — restart recency cannot be determined, treated as not recent",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        _create_pod_with_untimed_restart("rook-ceph-osd-0", restarts=3),
                    ]
                ),
            },
        ),
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
                        create_pod_mock(
                            "rook-ceph-osd-0", phase="Running", ready=False, waiting_reason="CrashLoopBackOff"
                        ),
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

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
