"""Tests for etcd signer CA certificate expiry check."""

import json

import pytest

from in_cluster_checks.rules.security.etcd_ca_certificate_validations import EtcdCaExpiryCheck
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def _make_alerts_json(alerts):
    """Build a JSON response mimicking Prometheus /api/v1/alerts output.

    Args:
        alerts: List of (alertname, severity, state) tuples.
    """
    items = []
    for alertname, severity, state in alerts:
        items.append({
            "labels": {"alertname": alertname, "severity": severity},
            "state": state,
            "activeAt": "2026-08-01T00:00:00Z",
            "value": "1",
        })
    return json.dumps({"status": "success", "data": {"alerts": items}})


_POD_NAME = "prometheus-k8s-0"

_GET_POD_KEY = (
    "get",
    ("pods", "-n", "openshift-monitoring", "-l", "app.kubernetes.io/name=prometheus",
     "-o", "jsonpath={.items[0].metadata.name}"),
)

_EXEC_KEY = (
    "exec",
    ("-n", "openshift-monitoring", _POD_NAME, "-c", "prometheus", "--",
     "curl", "-s", "http://localhost:9090/api/v1/alerts"),
)


def _scenario(title, alerts_json, failed_msg=None):
    """Build a scenario that sets cached pod name and mocks the alerts query."""
    return RuleScenarioParams(
        title,
        oc_cmd_output_dict={
            _EXEC_KEY: CmdOutput(alerts_json),
        },
        tested_object_mock_dict={"_prometheus_pod_name": _POD_NAME},
        failed_msg=failed_msg,
    )


class TestEtcdCaExpiryCheck(RuleTestBase):
    """Test EtcdCaExpiryCheck rule."""

    tested_type = EtcdCaExpiryCheck

    scenario_passed = [
        _scenario(
            "no alerts firing at all",
            _make_alerts_json([]),
        ),
        _scenario(
            "unrelated alert firing, no etcd CA alerts",
            _make_alerts_json([("SomeOtherAlert", "critical", "firing")]),
        ),
        _scenario(
            "etcd CA critical alert present but only pending (not firing)",
            _make_alerts_json([("etcdSignerCAExpirationCritical", "critical", "pending")]),
        ),
    ]

    scenario_warning = [
        _scenario(
            "warning alert firing (~2 years remaining)",
            _make_alerts_json([("etcdSignerCAExpirationWarning", "warning", "firing")]),
        ),
    ]

    scenario_failed = [
        _scenario(
            "critical alert firing (~1 year remaining)",
            _make_alerts_json([("etcdSignerCAExpirationCritical", "critical", "firing")]),
            failed_msg=(
                "CRITICAL: etcd signer CA certificate is expiring - alert "
                "'etcdSignerCAExpirationCritical' is firing (~1 year or less remaining).\n"
                "If the etcd signer CA expires, all etcd certificates become invalid "
                "and the control plane goes down. Rotate the etcd signer CA before it expires."
            ),
        ),
        _scenario(
            "both warning and critical firing -> critical wins (FAILED)",
            _make_alerts_json([
                ("etcdSignerCAExpirationWarning", "warning", "firing"),
                ("etcdSignerCAExpirationCritical", "critical", "firing"),
            ]),
            failed_msg=(
                "CRITICAL: etcd signer CA certificate is expiring - alert "
                "'etcdSignerCAExpirationCritical' is firing (~1 year or less remaining).\n"
                "If the etcd signer CA expires, all etcd certificates become invalid "
                "and the control plane goes down. Rotate the etcd signer CA before it expires."
            ),
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "malformed JSON from alerts query",
            oc_cmd_output_dict={_EXEC_KEY: CmdOutput("not-json")},
            tested_object_mock_dict={"_prometheus_pod_name": _POD_NAME},
        ),
        RuleScenarioParams(
            "prometheus returns error status in response",
            oc_cmd_output_dict={
                _EXEC_KEY: CmdOutput(json.dumps({"status": "error", "error": "invalid query"})),
            },
            tested_object_mock_dict={"_prometheus_pod_name": _POD_NAME},
        ),
    ]

    def test_prerequisite_not_met_no_prometheus_pod(self, tested_object):
        """Test prerequisite returns not_met when no Prometheus pod found."""
        scenario = RuleScenarioParams(
            "prometheus pod not found",
            oc_cmd_output_dict={_GET_POD_KEY: CmdOutput("")},
        )
        self._init_validation_object(tested_object, scenario)
        result = tested_object.is_prerequisite_fulfilled()
        assert not result.fulfilled

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)
