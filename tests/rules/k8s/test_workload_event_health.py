from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.k8s.workload_event_health import (
    MAX_DETAILS_IN_MESSAGE,
    WorkloadEventCollector,
    WorkloadEventHealth,
)
from tests.pytest_tools.test_data_collector_base import DataCollectorScenarioParams, DataCollectorTestBase
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def _create_event(
    namespace: str = "default",
    name: str = "some-event",
    type_: str = "Warning",
    reason: str = "BackOff",
    message: str = "back-off restarting failed container",
    count: int = 1,
    kind: str = "Pod",
    obj_name: str = "some-pod",
    obj_namespace: str | None = None,
    first_timestamp: str | None = "2026-11-01T00:00:00Z",
    last_timestamp: str | None = "2026-11-01T00:05:00Z",
    source_component: str | None = "kubelet",
) -> dict:
    """Build an already-parsed event dict, matching WorkloadEventCollector output shape."""
    return {
        "namespace": namespace,
        "name": name,
        "type": type_,
        "reason": reason,
        "message": message,
        "count": count,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "source_component": source_component,
        "involved_object": {
            "kind": kind,
            "name": obj_name,
            "namespace": obj_namespace if obj_namespace is not None else namespace,
        },
    }


class TestWorkloadEventHealth(RuleTestBase):
    """Test WorkloadEventHealth orchestrator rule."""

    tested_type = WorkloadEventHealth

    def _assert_required_fields(self, data_dict, required_fields, context=""):
        """Assert all required fields exist in data dictionary."""
        assert set(required_fields).issubset(data_dict.keys()), (
            f"Missing fields{' in ' + context if context else ''}. "
            f"Expected: {required_fields}, Got: {list(data_dict.keys())}"
        )

    no_events = {"events": []}

    only_benign_events = {
        "events": [
            _create_event(type_="Normal", reason="Scheduled", kind="Pod", obj_name="pod-a"),
            _create_event(type_="Warning", reason="ScalingReplicaSet", kind="Deployment", obj_name="dep-a"),
        ]
    }

    node_warning_excluded = {
        "events": [
            _create_event(type_="Warning", reason="Unhealthy", kind="Node", obj_name="worker-1"),
        ]
    }

    single_unhealthy_event = {
        "events": [
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="BackOff",
                message="Back-off restarting failed container",
                count=3,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
        ]
    }

    # Two Warning events on the SAME pod — should aggregate into one workload entry
    same_pod_multiple_events = {
        "events": [
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="BackOff",
                message="m1",
                count=5,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="CrashLoopBackOff",
                message="m2",
                count=3,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
        ]
    }

    multiple_workloads_unhealthy = {
        "events": [
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="BackOff",
                message="m1",
                count=1,
                kind="Pod",
                obj_name="my-pod1",
                obj_namespace="ns1",
            ),
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="OOMKilling",
                message="m2",
                count=1,
                kind="Pod",
                obj_name="my-pod2",
                obj_namespace="ns1",
            ),
            _create_event(
                namespace="ns2",
                type_="Warning",
                reason="FailedCreate",
                message="m3",
                count=1,
                kind="Deployment",
                obj_name="dep1",
                obj_namespace="ns2",
            ),
        ]
    }

    scenario_info = [
        RuleScenarioParams(
            "no events at all",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": no_events},
            },
            info_msg="Workload events: 0 workload(s) with events\nNo unhealthy workloads detected",
        ),
        RuleScenarioParams(
            "only benign/normal events - no unhealthy workloads",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": only_benign_events},
            },
            info_msg="Workload events: 2 workload(s) with events\nNo unhealthy workloads detected",
        ),
        RuleScenarioParams(
            "Warning event on Node excluded from workload aggregation",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": node_warning_excluded},
            },
            info_msg="Workload events: 0 workload(s) with events\nNo unhealthy workloads detected",
        ),
        RuleScenarioParams(
            "single unhealthy workload",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": single_unhealthy_event},
            },
            info_msg=(
                "Workload events: 1 workload(s) with events, 1 unhealthy:\n"
                "\n"
                "ns1/Pod/my-pod\n"
                "  Reasons: BackOff\n"
                "  Events: 3 total, 3 warning"
            ),
        ),
        RuleScenarioParams(
            "same pod has two unhealthy reasons - aggregated into one workload entry",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": same_pod_multiple_events},
            },
            info_msg=(
                "Workload events: 1 workload(s) with events, 1 unhealthy:\n"
                "\n"
                "ns1/Pod/my-pod\n"
                "  Reasons: BackOff, CrashLoopBackOff\n"
                "  Events: 8 total, 8 warning"
            ),
        ),
        RuleScenarioParams(
            "multiple unhealthy workloads across namespaces",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": multiple_workloads_unhealthy},
            },
            info_msg=(
                "Workload events: 3 workload(s) with events, 3 unhealthy:\n"
                "\n"
                "ns1/Pod/my-pod1\n"
                "  Reasons: BackOff\n"
                "  Events: 1 total, 1 warning\n"
                "ns1/Pod/my-pod2\n"
                "  Reasons: OOMKilling\n"
                "  Events: 1 total, 1 warning\n"
                "ns2/Deployment/dep1\n"
                "  Reasons: FailedCreate\n"
                "  Events: 1 total, 1 warning"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_info)
    def test_scenario_info(self, scenario_params, tested_object):
        """Test rule returns INFO status with workload-level aggregated data."""
        # Verify status/message using base test
        RuleTestBase.test_scenario_info(self, scenario_params, tested_object)

        # Verify data payload structure
        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

            # Verify extra fields follow the ResourcesUtilization pattern
            assert "workload_events_data" in result.extra
            assert result.extra["html_tab"] == "workload_event_health"
            assert isinstance(result.extra["is_uniform"], bool)

            data = result.extra["workload_events_data"]
            self._assert_required_fields(data, ["workloads"], "workload_events_data")

            for workload in data["workloads"]:
                self._assert_required_fields(
                    workload,
                    [
                        "namespace",
                        "kind",
                        "name",
                        "total_events",
                        "warning_events",
                        "reasons",
                        "unhealthy_reasons",
                        "is_unhealthy",
                        "sample_message",
                    ],
                    "workload entry",
                )

    def test_is_uniform_true_when_no_unhealthy_workloads(self, tested_object):
        """is_uniform should be True when no workloads have unhealthy events."""
        scenario_params = RuleScenarioParams(
            "healthy scenario",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": self.only_benign_events},
            },
        )
        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()
            assert result.extra["is_uniform"] is True

    def test_is_uniform_false_when_unhealthy_workloads_present(self, tested_object):
        """is_uniform should be False when at least one workload is unhealthy."""
        scenario_params = RuleScenarioParams(
            "unhealthy scenario",
            cmd_input_output_dict={},
            data_collector_dict={
                WorkloadEventCollector: {"in-cluster-orchestrator": self.single_unhealthy_event},
            },
        )
        self._init_validation_object(tested_object, scenario_params)
        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()
            assert result.extra["is_uniform"] is False


class TestWorkloadEventHealthAggregation:
    """Unit tests for WorkloadEventHealth aggregation and message building."""

    @pytest.fixture
    def rule(self):
        """Create a WorkloadEventHealth instance with a mocked host_executor."""
        return WorkloadEventHealth(host_executor=Mock())

    def test_aggregate_excludes_non_workload_kinds(self, rule):
        """Node/Namespace events are excluded from the workload aggregation."""
        events = [
            _create_event(type_="Warning", reason="Unhealthy", kind="Node", obj_name="node-1"),
            _create_event(type_="Warning", reason="BackOff", kind="Pod", obj_name="my-pod"),
        ]
        workloads = rule._aggregate_by_workload(events)
        assert len(workloads) == 1
        assert workloads[0]["kind"] == "Pod"

    def test_aggregate_groups_events_on_same_object(self, rule):
        """Multiple events on the same object are collapsed into one workload entry."""
        events = [
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="BackOff",
                count=3,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
            _create_event(
                namespace="ns1",
                type_="Warning",
                reason="CrashLoopBackOff",
                count=2,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
            _create_event(
                namespace="ns1",
                type_="Normal",
                reason="Scheduled",
                count=1,
                kind="Pod",
                obj_name="my-pod",
                obj_namespace="ns1",
            ),
        ]
        workloads = rule._aggregate_by_workload(events)
        assert len(workloads) == 1

        w = workloads[0]
        assert w["namespace"] == "ns1"
        assert w["kind"] == "Pod"
        assert w["name"] == "my-pod"
        assert w["total_events"] == 6  # 3 + 2 + 1
        assert w["warning_events"] == 5  # 3 + 2
        assert w["reasons"] == {"BackOff": 3, "CrashLoopBackOff": 2, "Scheduled": 1}
        assert w["unhealthy_reasons"] == ["BackOff", "CrashLoopBackOff"]
        assert w["is_unhealthy"] is True
        assert w["sample_message"] == "back-off restarting failed container"  # from first unhealthy event

    def test_aggregate_benign_warnings_are_not_unhealthy(self, rule):
        """Warning events with reasons NOT in UNHEALTHY_REASONS don't make a workload unhealthy."""
        events = [
            _create_event(type_="Warning", reason="ScalingReplicaSet", kind="Deployment", obj_name="dep-a"),
        ]
        workloads = rule._aggregate_by_workload(events)
        assert len(workloads) == 1
        assert workloads[0]["is_unhealthy"] is False
        assert workloads[0]["unhealthy_reasons"] == []
        assert workloads[0]["sample_message"] == ""  # no unhealthy events, empty sample

    def test_aggregate_sorts_by_namespace_kind_name(self, rule):
        """Workload entries are sorted by (namespace, kind, name)."""
        events = [
            _create_event(namespace="z-ns", kind="Pod", obj_name="pod-a", obj_namespace="z-ns"),
            _create_event(namespace="a-ns", kind="Pod", obj_name="pod-b", obj_namespace="a-ns"),
            _create_event(namespace="a-ns", kind="Deployment", obj_name="dep-a", obj_namespace="a-ns"),
        ]
        workloads = rule._aggregate_by_workload(events)
        keys = [(w["namespace"], w["kind"], w["name"]) for w in workloads]
        assert keys == [("a-ns", "Deployment", "dep-a"), ("a-ns", "Pod", "pod-b"), ("z-ns", "Pod", "pod-a")]

    def test_format_workload_detail(self, rule):
        """_format_workload_detail renders multi-line block with ref, reasons, counts."""
        workload = {
            "namespace": "ns1",
            "kind": "Deployment",
            "name": "my-app",
            "total_events": 42,
            "warning_events": 30,
            "reasons": {"BackOff": 20, "Scheduled": 12},
            "unhealthy_reasons": ["BackOff", "CrashLoopBackOff"],
            "is_unhealthy": True,
        }
        result = rule._format_workload_detail(workload)
        expected = "ns1/Deployment/my-app\n  Reasons: BackOff, CrashLoopBackOff\n  Events: 42 total, 30 warning"
        assert result == expected

    def test_build_message_truncates_long_detail_lists(self, rule):
        """More than MAX_DETAILS_IN_MESSAGE unhealthy workloads get a '... and N more' suffix."""
        extra_count = 2
        total_unhealthy = MAX_DETAILS_IN_MESSAGE + extra_count

        # Build events: one unique Pod per event, all unhealthy
        all_events = [
            _create_event(
                namespace="ns1",
                reason="BackOff",
                count=1,
                kind="Pod",
                obj_name=f"pod-{i}",
                obj_namespace="ns1",
            )
            for i in range(total_unhealthy)
        ]

        workloads = rule._aggregate_by_workload(all_events)
        unhealthy_workloads = [w for w in workloads if w["is_unhealthy"]]
        assert len(unhealthy_workloads) == total_unhealthy

        message = rule._build_message(workloads, unhealthy_workloads)

        assert f"... and {extra_count} more unhealthy workload(s)" in message
        assert message.count("pod-") == MAX_DETAILS_IN_MESSAGE
        assert f"{total_unhealthy} unhealthy:" in message

    def test_build_message_no_unhealthy(self, rule):
        """Message when all workloads are healthy."""
        events = [
            _create_event(type_="Normal", reason="Scheduled", kind="Pod", obj_name="pod-a"),
        ]
        workloads = rule._aggregate_by_workload(events)
        unhealthy = [w for w in workloads if w["is_unhealthy"]]
        message = rule._build_message(workloads, unhealthy)
        assert "No unhealthy workloads detected" in message


class TestWorkloadEventCollector(DataCollectorTestBase):
    """Test WorkloadEventCollector data collector."""

    tested_type = WorkloadEventCollector

    def _make_event_mock(self, event_dict: dict) -> Mock:
        """Create a Mock event APIObject whose as_dict() returns the given dict."""
        mock_event = Mock()
        mock_event.as_dict.return_value = event_dict
        return mock_event

    full_event_dict = {
        "metadata": {"name": "my-pod.1234", "namespace": "ns1"},
        "type": "Warning",
        "reason": "BackOff",
        "message": "Back-off restarting failed container",
        "count": 7,
        "firstTimestamp": "2026-11-01T00:00:00Z",
        "lastTimestamp": "2026-11-01T00:05:00Z",
        "source": {"component": "kubelet"},
        "involvedObject": {"kind": "Pod", "name": "my-pod", "namespace": "ns1"},
    }

    minimal_event_dict = {
        "metadata": {"name": "my-pod.5678", "namespace": "ns1"},
        "type": "Warning",
        "reason": "FailedScheduling",
        "message": "0/3 nodes are available",
        "involvedObject": {"kind": "Pod", "name": "my-pod"},
    }

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="no events found on the cluster",
            cmd_input_output_dict={},
            tested_object_mock_dict={
                "oc_api.select_resources": Mock(return_value=[]),
            },
            scenario_res={"events": []},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test WorkloadEventCollector.collect_data() with no events."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def test_collect_data_parses_full_event(self):
        """collect_data() parses all fields of a fully populated event."""
        collector = WorkloadEventCollector(host_executor=Mock())
        collector.oc_api.select_resources = Mock(return_value=[self._make_event_mock(self.full_event_dict)])

        result = collector.collect_data()

        assert result == {
            "events": [
                {
                    "namespace": "ns1",
                    "name": "my-pod.1234",
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": "Back-off restarting failed container",
                    "count": 7,
                    "first_timestamp": "2026-11-01T00:00:00Z",
                    "last_timestamp": "2026-11-01T00:05:00Z",
                    "source_component": "kubelet",
                    "involved_object": {"kind": "Pod", "name": "my-pod", "namespace": "ns1"},
                }
            ]
        }

    def test_collect_data_defaults_missing_optional_fields(self):
        """collect_data() fills in sane defaults when optional event fields are missing."""
        collector = WorkloadEventCollector(host_executor=Mock())
        collector.oc_api.select_resources = Mock(return_value=[self._make_event_mock(self.minimal_event_dict)])

        result = collector.collect_data()

        event = result["events"][0]
        assert event["count"] == 1
        assert event["first_timestamp"] is None
        assert event["last_timestamp"] is None
        assert event["source_component"] is None
        assert event["involved_object"] == {"kind": "Pod", "name": "my-pod", "namespace": None}

    def test_collect_data_no_events(self):
        """collect_data() returns an empty events list when there are no events."""
        collector = WorkloadEventCollector(host_executor=Mock())
        collector.oc_api.select_resources = Mock(return_value=[])

        result = collector.collect_data()

        assert result == {"events": []}
