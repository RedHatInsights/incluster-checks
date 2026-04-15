"""Tests for kubelet CA certificate expiry check."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from in_cluster_checks.rules.security.ca_certificate_expiry import KubeletCaExpiryCheck
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def _generate_cert_pem(days_until_expiry):
    """Generate a self-signed certificate with specified expiry."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "kube-apiserver-to-kubelet-signer"),
    ])

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=365))
        .not_valid_after(now + timedelta(days=days_until_expiry))
        .sign(private_key, hashes.SHA256())
    )

    return cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')


def _make_kubelet_ca_secret_json(days_until_expiry):
    """Create a mock secret JSON with a certificate."""
    cert_pem = _generate_cert_pem(days_until_expiry)
    cert_b64 = base64.b64encode(cert_pem.encode()).decode()

    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "kube-apiserver-to-kubelet-signer",
            "namespace": "openshift-kube-apiserver-operator",
        },
        "data": {
            "tls.crt": cert_b64,
            "tls.key": "fake-key",
        },
    }

    return json.dumps(secret)


class TestKubeletCaExpiryCheck(RuleTestBase):
    """Test KubeletCaExpiryCheck rule."""

    tested_type = KubeletCaExpiryCheck

    # Generate certificates and get their expiry dates for test assertions
    _valid_days = 100
    _expiring_days = 20
    _expired_days = -5

    # Valid CA certificate (100 days remaining)
    oc_get_secret_valid = _make_kubelet_ca_secret_json(days_until_expiry=_valid_days)

    # CA expiring soon (20 days remaining - below 30 day threshold)
    oc_get_secret_expiring = _make_kubelet_ca_secret_json(days_until_expiry=_expiring_days)

    # CA already expired (-5 days)
    oc_get_secret_expired = _make_kubelet_ca_secret_json(days_until_expiry=_expired_days)

    # Calculate expected dates for assertions
    _now = datetime.now(timezone.utc)
    _expiring_date = (_now + timedelta(days=_expiring_days)).strftime("%Y-%m-%d %H:%M:%S UTC")
    _expired_date = (_now + timedelta(days=_expired_days)).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Secret with missing tls.crt
    oc_get_secret_missing_cert = json.dumps({
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "kube-apiserver-to-kubelet-signer",
            "namespace": "openshift-kube-apiserver-operator",
        },
        "data": {
            "tls.key": "fake-key",
        },
    })

    # Invalid certificate data
    oc_get_secret_invalid_cert = json.dumps({
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "kube-apiserver-to-kubelet-signer",
            "namespace": "openshift-kube-apiserver-operator",
        },
        "data": {
            "tls.crt": "aW52YWxpZC1jZXJ0aWZpY2F0ZQ==",  # "invalid-certificate" in base64
        },
    })

    oc_cmd_key = ("get", ("secret", "kube-apiserver-to-kubelet-signer", "-n", "openshift-kube-apiserver-operator", "-o", "json"))

    # Build scenarios with correct dates
    scenario_passed = [
        RuleScenarioParams(
            "CA certificate valid (100+ days remaining)",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(oc_get_secret_valid)},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "CA certificate expiring soon (20 days < 30 day threshold)",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(oc_get_secret_expiring)},
            failed_msg=(
                f"CRITICAL: Kubelet CA certificate expires in 19 days (threshold: 30 days)\n"
                f"Secret: openshift-kube-apiserver-operator/kube-apiserver-to-kubelet-signer\n"
                f"Expiry Date: {_expiring_date}\n\n"
                f"CA rotation should have happened at ~73 days remaining (~292 days after creation).\n"
                f"This means CA auto-rotation has been failing for ~273 days.\n"
                f"If CA expires, ALL kubelet certificates become invalid, breaking cluster authentication."
            ),
        ),
        RuleScenarioParams(
            "CA certificate expired",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(oc_get_secret_expired)},
            failed_msg=(
                f"CRITICAL: Kubelet CA certificate EXPIRED 6 days ago!\n"
                f"Secret: openshift-kube-apiserver-operator/kube-apiserver-to-kubelet-signer\n"
                f"Expiry Date: {_expired_date}\n\n"
                f"All kubelet node certificates are invalid. Cluster authentication is broken."
            ),
        ),
        RuleScenarioParams(
            "Secret missing tls.crt data",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(oc_get_secret_missing_cert)},
            failed_msg="Failed to parse kubelet CA certificate: No tls.crt data found in secret openshift-kube-apiserver-operator/kube-apiserver-to-kubelet-signer",
        ),
        RuleScenarioParams(
            "Invalid certificate data",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(oc_get_secret_invalid_cert)},
            failed_msg="Failed to parse kubelet CA certificate: Failed to parse certificate: Unable to load PEM file. See https://cryptography.io/en/latest/faq/#why-can-t-i-import-my-pem-file for more details. MalformedFraming",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
