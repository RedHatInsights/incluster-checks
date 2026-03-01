"""
Tests for certificate expiry validations.

Ported from support/HealthChecks/flows/Security/Certificate/allcertificate_expiry_dates.py
"""

from datetime import datetime, timedelta

import pytest

from in_cluster_checks.rules.security.certificate_expiry import NodeCertificateExpiry
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


class TestNodeCertificateExpiry(RuleTestBase):
    """Test NodeCertificateExpiry validator."""

    tested_type = NodeCertificateExpiry

    # Common certificate path for testing
    cert_path = "/var/lib/kubelet/pki/kubelet-client-current.pem"

    # Generate dates for testing
    now = datetime.now()
    expired_date = (now - timedelta(days=30)).strftime("%b %d %H:%M:%S %Y")
    expiring_soon_date = (now + timedelta(days=20)).strftime("%b %d %H:%M:%S %Y")
    valid_date = (now + timedelta(days=365)).strftime("%b %d %H:%M:%S %Y")

    # Command outputs
    which_openssl = "which openssl"

    # Mock all glob expansion commands for CERT_PATHS
    glob_expansion_commands = {
        "ls /var/lib/kubelet/pki/kubelet-client-current.pem 2>/dev/null": CmdOutput(
            out="/var/lib/kubelet/pki/kubelet-client-current.pem", return_code=0
        ),
        "ls /var/lib/kubelet/pki/kubelet-server-current.pem 2>/dev/null": CmdOutput(
            out="", return_code=1
        ),  # Not found
        "ls /etc/kubernetes/static-pod-certs/secrets/etcd-all-certs/etcd-serving-*.crt 2>/dev/null": CmdOutput(
            out="", return_code=1
        ),  # Not found
        "ls /etc/kubernetes/static-pod-certs/secrets/etcd-all-certs/etcd-peer-*.crt 2>/dev/null": CmdOutput(
            out="", return_code=1
        ),  # Not found
    }

    # Mock file existence checks (used by file_utils.is_file_exist)
    # Only kubelet-client-current.pem exists in our test scenario
    file_existence_commands = {
        "ls /var/lib/kubelet/pki/kubelet-client-current.pem": CmdOutput(
            out="/var/lib/kubelet/pki/kubelet-client-current.pem", return_code=0
        ),
        "ls /var/lib/kubelet/pki/kubelet-server-current.pem": CmdOutput(out="", return_code=1),
    }

    prerequisite_commands = {
        which_openssl: CmdOutput(out="/usr/bin/openssl", return_code=0),
    }

    scenario_passed = [
        RuleScenarioParams(
            "certificate valid for 1+ year",
            {
                **prerequisite_commands,
                **glob_expansion_commands,
                **file_existence_commands,
                f"openssl x509 -enddate -noout -in {cert_path}": CmdOutput(
                    out=f"notAfter={valid_date} GMT", return_code=0
                ),
            },
        ),
    ]

    # Calculate exact expected messages (messages depend on days calculation)
    expiring_days = (datetime.strptime(expiring_soon_date, "%b %d %H:%M:%S %Y") - now).days

    scenario_warning = [
        RuleScenarioParams(
            "certificate expiring within 30 days",
            {
                **prerequisite_commands,
                **glob_expansion_commands,
                **file_existence_commands,
                f"openssl x509 -enddate -noout -in {cert_path}": CmdOutput(
                    out=f"notAfter={expiring_soon_date} GMT", return_code=0
                ),
            },
            failed_msg=f"Found 1 certificate(s) expiring within 30 days:\n  - {cert_path} ({expiring_days} days)",
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "certificate expired",
            {
                **prerequisite_commands,
                **glob_expansion_commands,
                **file_existence_commands,
                f"openssl x509 -enddate -noout -in {cert_path}": CmdOutput(
                    out=f"notAfter={expired_date} GMT", return_code=0
                ),
            },
            failed_msg=f"Found 1 expired certificate(s) on node:\n  - {cert_path}",
        ),
        RuleScenarioParams(
            "openssl command fails",
            {
                **prerequisite_commands,
                **glob_expansion_commands,
                **file_existence_commands,
                f"openssl x509 -enddate -noout -in {cert_path}": CmdOutput(
                    out="", err="unable to load certificate", return_code=1
                ),
            },
            failed_msg=f"Failed to check 1 certificate(s):\n  - {cert_path}",
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
