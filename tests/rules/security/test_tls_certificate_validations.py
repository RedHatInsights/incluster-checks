"""
Tests for TLS certificate expiry validation rule.

Ported from HealthChecks TlsCertificateExpiryValidator.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from in_cluster_checks.rules.security.tls_certificate_validations import TlsCertificateExpiry
from in_cluster_checks.utils.enums import Status
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


def _generate_cert_pem(days_valid=365, days_expired=0):
    """Generate a self-signed PEM certificate for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])

    now = datetime.now(timezone.utc)
    if days_expired > 0:
        not_before = now - timedelta(days=days_expired + days_valid)
        not_after = now - timedelta(days=days_expired)
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
    for name, namespace, cert_pem in secrets:
        cert_b64 = base64.b64encode(cert_pem.encode()).decode() if cert_pem else ""
        items.append({
            "metadata": {"name": name, "namespace": namespace},
            "data": {"tls.crt": cert_b64},
        })
    return json.dumps({"items": items})


# Pre-generate certificates for test scenarios
_valid_cert = _generate_cert_pem(days_valid=365)
_expiring_cert = _generate_cert_pem(days_valid=5)
_expired_cert = _generate_cert_pem(days_valid=30, days_expired=5)


class TestTlsCertificateExpiry(RuleTestBase):
    """Test TlsCertificateExpiry rule."""

    tested_type = TlsCertificateExpiry

    oc_get_cmd = ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json"))

    scenario_passed = [
        RuleScenarioParams(
            "all certificates valid",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    _make_secrets_json([
                        ("my-tls-secret", "default", _valid_cert),
                        ("another-tls", "kube-system", _valid_cert),
                    ])
                ),
            },
        ),
        RuleScenarioParams(
            "no TLS secrets in cluster",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    json.dumps({"items": []})
                ),
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "certificate expiring within 14 days",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    _make_secrets_json([
                        ("expiring-secret", "default", _expiring_cert),
                    ])
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "certificate already expired",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    _make_secrets_json([
                        ("expired-secret", "my-namespace", _expired_cert),
                    ])
                ),
            },
        ),
        RuleScenarioParams(
            "secret has no tls.crt data and no valid certs",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    json.dumps({"items": [{
                        "metadata": {"name": "bad-secret", "namespace": "default"},
                        "data": {"tls.crt": ""},
                    }]})
                ),
            },
            failed_msg="Failed to check 1 TLS certificate(s)",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "oc get secret command fails",
            oc_cmd_output_dict={
                ("get", ("secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json")): CmdOutput(
                    "", return_code=1, err="Unable to connect to the server"
                ),
            },
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
