"""Orchestrator rule for Kubernetes/OpenShift workload event health reporting."""

from collections import defaultdict
from typing import Any, Dict, List

from in_cluster_checks.core.operations import OrchestratorDataCollector
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives

# Resource kinds that represent actual workloads. Node/Namespace events are
# covered by dedicated node/namespace health rules and are intentionally
# excluded from the aggregation below.
WORKLOAD_KINDS = {
    "Pod",
    "Deployment",
    "ReplicaSet",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
}

# Warning event "reason" values that indicate a real workload problem, as
# opposed to benign/expected Warning noise (e.g. "ScalingReplicaSet").
# Non-exhaustive - covers the most common failure modes seen in practice.
UNHEALTHY_REASONS = {
    "BackOff",
    "CrashLoopBackOff",
    "Failed",
    "FailedCreate",
    "FailedMount",
    "FailedAttachVolume",
    "FailedScheduling",
    "FailedSync",
    "Unhealthy",
    "OOMKilling",
    "Evicted",
    "NetworkNotReady",
    "ProbeWarning",
    "ImagePullBackOff",
    "ErrImagePull",
}

# Cap on how many workload lines are rendered in the summary message,
# to keep the message readable when a cluster has many unhealthy workloads
# (the full list is always available in workload_events_data).
MAX_DETAILS_IN_MESSAGE = 15


class WorkloadEventCollector(OrchestratorDataCollector):
    """Collect all Kubernetes events across all namespaces."""

    unique_name = "collect_workload_events"
    title = "Collect Workload Events Data"

    def collect_data(self, **kwargs) -> Dict[str, Any]:
        """Collect all cluster events via 'oc get events --all-namespaces'.

        Returns:
            Dict containing all parsed events: {"events": [...]}
        """
        event_objects = self.oc_api.select_resources("event", all_namespaces=True, timeout=45)

        events = [self._parse_event(event_obj) for event_obj in event_objects]

        return {"events": events}

    def _parse_event(self, event_obj: Any) -> Dict[str, Any]:
        """Convert an Event APIObject into a plain, JSON-serializable dict.

        Args:
            event_obj: Event APIObject from openshift_client

        Returns:
            Dict with the fields needed for health evaluation and JSON reporting
        """
        event_dict = event_obj.as_dict()
        metadata = event_dict.get("metadata", {})
        involved_object = event_dict.get("involvedObject", {})
        source = event_dict.get("source", {})

        return {
            "namespace": metadata.get("namespace"),
            "name": metadata.get("name"),
            "type": event_dict.get("type", "Normal"),
            "reason": event_dict.get("reason", ""),
            "message": event_dict.get("message", ""),
            "count": event_dict.get("count") or 1,
            "first_timestamp": event_dict.get("firstTimestamp"),
            "last_timestamp": event_dict.get("lastTimestamp") or event_dict.get("eventTime"),
            "source_component": source.get("component"),
            "involved_object": {
                "kind": involved_object.get("kind"),
                "name": involved_object.get("name"),
                "namespace": involved_object.get("namespace"),
            },
        }


class WorkloadEventHealth(OrchestratorRule):
    """Report Kubernetes event health aggregated at the workload level.

    Collects all cluster events, then aggregates them by workload object
    (namespace + kind + name).  Each workload entry summarises its total
    event count, warning count, unhealthy reasons, and whether it is
    considered unhealthy.  This keeps the JSON compact — one entry per
    workload instead of one per raw event — following the same pattern
    used by ResourcesUtilization (one entry per node).

    Non-workload events (e.g. Node, Namespace) are excluded from the
    output since they are covered by dedicated rules.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "workload_event_health"
    title = "Workload Event Health"
    links = ["https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418417677/In-Cluster+Checks+Rules"]

    def run_rule(self) -> RuleResult:
        """Coordinate collection and build the workload-level event health report.

        Returns:
            RuleResult with INFO status containing workload-aggregated event
            data (JSON) plus a summary message highlighting unhealthy workloads.
        """
        event_data = self.run_data_collector(WorkloadEventCollector)

        # Collector returns: {'in-cluster-orchestrator': {'events': [...]}}
        all_events = list(event_data.values())[0].get("events", []) if event_data else []

        # Aggregate raw events into workload-level summaries
        workloads = self._aggregate_by_workload(all_events)
        unhealthy_workloads = [w for w in workloads if w["is_unhealthy"]]

        workload_events_data = {
            "workloads": workloads,
        }

        message = self._build_message(workloads, unhealthy_workloads)

        return RuleResult.info(
            message=message,
            workload_events_data=workload_events_data,  # Workload-level event data for special tab
            html_tab="workload_event_health",  # Hint for HTML report generator
            is_uniform=len(unhealthy_workloads) == 0,  # Quick check: no unhealthy workloads
        )

    def _aggregate_by_workload(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate raw events into one summary per workload object.

        Only events whose involvedObject.kind is in WORKLOAD_KINDS are
        included.  Each workload entry contains counts, reason breakdown,
        and an is_unhealthy flag.

        Args:
            events: All parsed events from the collector

        Returns:
            List of workload summary dicts, sorted by (namespace, kind, name)
        """
        groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            kind = event["involved_object"]["kind"]
            if kind not in WORKLOAD_KINDS:
                continue
            key = (
                event["involved_object"]["namespace"],
                kind,
                event["involved_object"]["name"],
            )
            groups[key].append(event)

        workloads = []
        for (namespace, kind, name), group_events in sorted(groups.items()):
            total_count = sum(e["count"] for e in group_events)
            warning_events = [e for e in group_events if e["type"] == "Warning"]
            warning_count = sum(e["count"] for e in warning_events)

            # Build reason breakdown: {"BackOff": 12, "Scheduled": 3, ...}
            reasons: Dict[str, int] = defaultdict(int)
            for e in group_events:
                reasons[e["reason"]] += e["count"]

            # Determine unhealthy reasons present
            unhealthy_reasons_found = sorted({e["reason"] for e in warning_events if e["reason"] in UNHEALTHY_REASONS})

            # Pick a sample message from the first unhealthy warning event
            unhealthy_warning_events = [e for e in warning_events if e["reason"] in UNHEALTHY_REASONS]
            sample_message = unhealthy_warning_events[0]["message"] if unhealthy_warning_events else ""

            workloads.append(
                {
                    "namespace": namespace,
                    "kind": kind,
                    "name": name,
                    "total_events": total_count,
                    "warning_events": warning_count,
                    "reasons": dict(sorted(reasons.items())),
                    "unhealthy_reasons": unhealthy_reasons_found,
                    "is_unhealthy": len(unhealthy_reasons_found) > 0,
                    "sample_message": sample_message,
                }
            )

        return workloads

    def _build_message(
        self,
        workloads: List[Dict[str, Any]],
        unhealthy_workloads: List[Dict[str, Any]],
    ) -> str:
        """Build the summary message for this rule.

        Args:
            workloads: All aggregated workload summaries
            unhealthy_workloads: Subset that have at least one unhealthy reason

        Returns:
            Formatted message string
        """
        total_workloads = len(workloads)

        if not unhealthy_workloads:
            return f"Workload events: {total_workloads} workload(s) with events\nNo unhealthy workloads detected"

        lines = [
            f"Workload events: {total_workloads} workload(s) with events, {len(unhealthy_workloads)} unhealthy:",
            "",
        ]
        for w in unhealthy_workloads[:MAX_DETAILS_IN_MESSAGE]:
            lines.append(self._format_workload_detail(w))
        remaining = len(unhealthy_workloads) - min(len(unhealthy_workloads), MAX_DETAILS_IN_MESSAGE)
        if remaining > 0:
            lines.append(f"\n... and {remaining} more unhealthy workload(s)")

        return "\n".join(lines)

    @staticmethod
    def _format_workload_detail(workload: Dict[str, Any]) -> str:
        """Format a single unhealthy workload as a multi-line block.

        Args:
            workload: Aggregated workload summary dict

        Returns:
            Formatted block, e.g.:
                ns1/Deployment/my-app
                  Reasons: BackOff, CrashLoopBackOff
                  Events: 42 total, 30 warning
        """
        ref = f"{workload['namespace']}/{workload['kind']}/{workload['name']}"
        reasons = ", ".join(workload["unhealthy_reasons"])
        return (
            f"{ref}\n"
            f"  Reasons: {reasons}\n"
            f"  Events: {workload['total_events']} total, {workload['warning_events']} warning"
        )
