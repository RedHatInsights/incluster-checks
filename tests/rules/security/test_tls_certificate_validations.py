"""
Tests for TLS certificate expiry validation rule.

Ported from HealthChecks TlsCertificateExpiryValidator.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import call

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from in_cluster_checks.rules.k8s.k8s_validations import InfraPodsReadyAndRunning
from in_cluster_checks.rules.security.tls_certificate_validations import TlsCertificateExpiry
from in_cluster_checks.utils.enums import Status
from in_cluster_checks.utils.infra_namespaces import COMMON_INFRA_NAMESPACES
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


def _generate_cert_pem(days_valid=365, days_expired=0, hours_valid=None, age_days=None):
    """Generate a self-signed PEM certificate for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])

    now = datetime.now(UTC)
    if days_expired > 0:
        not_before = now - timedelta(days=days_expired + days_valid)
        not_after = now - timedelta(days=days_expired)
    elif hours_valid is not None:
        not_before = now - timedelta(days=1)
        not_after = now + timedelta(hours=hours_valid)
    elif age_days is not None:
        not_before = now - timedelta(days=age_days)
        not_after = not_before + timedelta(days=days_valid)
    else:
        not_before = now
        not_after = now + timedelta(days=days_valid)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _make_secrets_json(secrets):
    """Build a JSON response mimicking 'oc get secret -o json' output."""
    items = []
    for secret in secrets:
        name, namespace, cert_pem = secret[:3]
        annotations = secret[3] if len(secret) > 3 else None
        cert_b64 = base64.b64encode(cert_pem.encode()).decode() if cert_pem else ""
        metadata = {"name": name, "namespace": namespace}
        if annotations:
            metadata["annotations"] = annotations
        items.append({
            "metadata": metadata,
            "data": {"tls.crt": cert_b64},
        })
    return json.dumps({"items": items})


# Pre-generate certificates for test scenarios
_valid_cert = _generate_cert_pem(days_valid=365)
_expiring_cert = _generate_cert_pem(days_valid=5)
_expired_cert = _generate_cert_pem(days_valid=30, days_expired=5)
# Edge cases: < 24h remaining (days=0 floor but still valid) and just outside 14-day warning window
_sub_day_cert = _generate_cert_pem(hours_valid=12)
_just_outside_warning_cert = _generate_cert_pem(hours_valid=14 * 24 + 1)

# Short-lived auto-rotating control-plane certs: 30-day validity, 15-day (360h) refresh period.
# Rotation is due at age 15d and may lag by refresh/10 (36h), so age 16d is still pending
# replacement while age 18d means rotation is genuinely overdue.
_ROTATION_ANNOTATIONS = {TlsCertificateExpiry.REFRESH_PERIOD_ANNOTATION: "360h0m0s"}
_BAD_ROTATION_ANNOTATIONS = {TlsCertificateExpiry.REFRESH_PERIOD_ANNOTATION: "not-a-duration"}
_rotating_in_window_cert = _generate_cert_pem(days_valid=30, age_days=16)
_rotating_overdue_cert = _generate_cert_pem(days_valid=30, age_days=18)
_rotating_expired_cert = _generate_cert_pem(days_valid=30, days_expired=5)


def _oc_outputs(namespace_outputs=None):
    """Provide one mocked secret-list response per TLS namespace."""
    namespace_outputs = namespace_outputs or {}
    return {
        ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-n", namespace, "-o", "json")):
            namespace_outputs.get(namespace, CmdOutput(_make_secrets_json([])))
        for namespace in TlsCertificateExpiry.INFRA_NAMESPACES
    }


@pytest.mark.parametrize(
    "value, expected",
    [
        ("360h0m0s", timedelta(hours=360)),
        ("1h30m0s", timedelta(hours=1, minutes=30)),
        ("45m", timedelta(minutes=45)),
        ("not-a-duration", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_go_duration(value, expected):
    """Read Go duration strings and reject anything unrecognized."""
    assert TlsCertificateExpiry._parse_go_duration(value) == expected


def test_shared_infrastructure_namespace_scope():
    """Keep overlapping rule scopes centralized and free of duplicates."""
    pod_namespaces = set(InfraPodsReadyAndRunning.INFRA_NAMESPACES)
    tls_namespaces = set(TlsCertificateExpiry.INFRA_NAMESPACES)

    assert pod_namespaces & tls_namespaces == set(COMMON_INFRA_NAMESPACES)
    assert len(pod_namespaces) == len(InfraPodsReadyAndRunning.INFRA_NAMESPACES)
    assert len(tls_namespaces) == len(TlsCertificateExpiry.INFRA_NAMESPACES)


class TestTlsCertificateExpiry(RuleTestBase):
    """Test TlsCertificateExpiry rule."""

    tested_type = TlsCertificateExpiry

    scenario_passed = [
        RuleScenarioParams(
            "all certificates valid",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ingress": CmdOutput(
                    _make_secrets_json([
                        ("router-tls", "openshift-ingress", _valid_cert),
                    ])
                ),
                "openshift-kube-apiserver": CmdOutput(
                    _make_secrets_json([("api-tls", "openshift-kube-apiserver", _valid_cert)])
                ),
                "openshift-config": CmdOutput(
                    _make_secrets_json([("console-tls", "openshift-config", _valid_cert)])
                ),
                "openshift-kube-controller-manager-operator": CmdOutput(
                    _make_secrets_json([("controller-signer", "openshift-kube-controller-manager-operator", _valid_cert)])
                ),
                "openshift-kube-scheduler": CmdOutput(
                    _make_secrets_json([("scheduler-serving", "openshift-kube-scheduler", _valid_cert)])
                ),
                "openshift-console": CmdOutput(
                    _make_secrets_json([("console-serving", "openshift-console", _valid_cert)])
                ),
                "openshift-ovn-kubernetes": CmdOutput(
                    _make_secrets_json([("ovn-serving", "openshift-ovn-kubernetes", _valid_cert)])
                ),
            }),
        ),
        RuleScenarioParams(
            "no TLS secrets in infrastructure namespaces",
            oc_cmd_output_dict=_oc_outputs(),
        ),
        RuleScenarioParams(
            "optional infrastructure namespace is absent",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ovn-kubernetes": CmdOutput(
                    "", return_code=1,
                    err='Error from server (NotFound): namespaces "openshift-ovn-kubernetes" not found',
                ),
            }),
        ),
        RuleScenarioParams(
            "certificate expiring in just over 14 days is not flagged as expiring soon",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ingress": CmdOutput(
                    _make_secrets_json([
                        ("router-tls", "openshift-ingress", _just_outside_warning_cert),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "auto-rotating certificate still inside its rotation window is not flagged",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-kube-scheduler": CmdOutput(
                    _make_secrets_json([
                        (
                            "kube-scheduler-client-cert-key",
                            "openshift-kube-scheduler",
                            _rotating_in_window_cert,
                            _ROTATION_ANNOTATIONS,
                        ),
                    ])
                ),
            }),
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "certificate expiring within 14 days",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-authentication": CmdOutput(
                    _make_secrets_json([
                        ("expiring-secret", "openshift-authentication", _expiring_cert),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "certificate with less than 24 hours remaining is treated as warning not expired",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ingress": CmdOutput(
                    _make_secrets_json([
                        ("router-tls", "openshift-ingress", _sub_day_cert),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "auto-rotating certificate past its rotation window is flagged",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-kube-scheduler": CmdOutput(
                    _make_secrets_json([
                        (
                            "kube-scheduler-client-cert-key",
                            "openshift-kube-scheduler",
                            _rotating_overdue_cert,
                            _ROTATION_ANNOTATIONS,
                        ),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "unparseable refresh-period annotation falls back to the expiry threshold",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-kube-scheduler": CmdOutput(
                    _make_secrets_json([
                        (
                            "kube-scheduler-client-cert-key",
                            "openshift-kube-scheduler",
                            _rotating_in_window_cert,
                            _BAD_ROTATION_ANNOTATIONS,
                        ),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "unparseable cert alongside a valid cert warns instead of passing",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ingress": CmdOutput(
                    _make_secrets_json([("valid-tls", "openshift-ingress", _valid_cert)])
                ),
                "openshift-config": CmdOutput(
                    json.dumps({"items": [{
                        "metadata": {"name": "bad-secret", "namespace": "openshift-config"},
                        "data": {"tls.crt": ""},
                    }]})
                ),
            }),
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "certificate already expired",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-etcd": CmdOutput(
                    _make_secrets_json([
                        ("expired-secret", "openshift-etcd", _expired_cert),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "expired certificate is still reported when auto-rotation is configured",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-etcd": CmdOutput(
                    _make_secrets_json([
                        ("expired-rotating", "openshift-etcd", _rotating_expired_cert, _ROTATION_ANNOTATIONS),
                    ])
                ),
            }),
        ),
        RuleScenarioParams(
            "secret has no tls.crt data and no valid certs",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-config": CmdOutput(
                    json.dumps({"items": [{
                        "metadata": {"name": "bad-secret", "namespace": "openshift-config"},
                        "data": {"tls.crt": ""},
                    }]})
                ),
            }),
            failed_msg="Failed to check 1 TLS certificate(s)",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "oc get secret command fails",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-monitoring": CmdOutput(
                    "", return_code=1, err="Unable to connect to the server"
                ),
            }),
        ),
        RuleScenarioParams(
            "secret access is forbidden",
            oc_cmd_output_dict=_oc_outputs({
                "openshift-ovn-kubernetes": CmdOutput(
                    "", return_code=1,
                    err="Error from server (Forbidden): secrets is forbidden",
                ),
            }),
        ),
    ]

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

    def test_rotation_window_suppresses_an_otherwise_firing_warning(self, tested_object):
        """Pass only because rotation is pending: the certificate is inside the warning threshold."""
        self._init_validation_object(tested_object, self.scenario_passed[4])

        result = tested_object.run_rule()

        assert result.status == Status.PASSED
        name, _, _, days_remaining, status = result.system_info["rows"][0]
        assert name == "kube-scheduler-client-cert-key"
        assert days_remaining <= TlsCertificateExpiry.WARNING_DAYS
        assert status == "ok"

    def test_reads_only_infra_namespaces(self, tested_object):
        """Query the approved namespaces once and combine their certificates."""
        self._init_validation_object(tested_object, self.scenario_passed[0])

        result = tested_object.run_rule()

        assert result.status == Status.PASSED
        assert tested_object.oc_api.run_oc_command.call_args_list == [
            call("get", ["secret", "--field-selector=type=kubernetes.io/tls", "-n", namespace, "-o", "json"])
            for namespace in (
                "openshift-etcd",
                "openshift-kube-apiserver",
                "openshift-kube-apiserver-operator",
                "openshift-kube-controller-manager",
                "openshift-kube-controller-manager-operator",
                "openshift-kube-scheduler",
                "openshift-apiserver",
                "openshift-ingress",
                "openshift-ingress-operator",
                "openshift-monitoring",
                "openshift-authentication",
                "openshift-controller-manager",
                "openshift-cluster-version",
                "openshift-machine-api",
                "openshift-machine-config-operator",
                "openshift-dns",
                "openshift-ovn-kubernetes",
                "openshift-multus",
                "openshift-network-operator",
                "openshift-image-registry",
                "openshift-oauth-apiserver",
                "openshift-marketplace",
                "openshift-console",
                "openshift-service-ca",
                "openshift-cluster-storage-operator",
                "openshift-config",
                "openshift-config-managed",
            )
        ]
        assert len(result.system_info["rows"]) == 7
