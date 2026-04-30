"""Tests for node certificate validations."""

import json
from datetime import datetime, timedelta

import pytest

from in_cluster_checks.rules.security.node_certificate_validations import (
    KubeletCsrHealthCheck,
    NodeCertificateExpiry,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


def _make_csr_json(csrs_list):
    """
    Create a mock CSR JSON response.

    Args:
        csrs_list: List of dictionaries with CSR data. Each dict should have:
            - name: CSR name
            - username: User that requested the CSR
            - conditions: List of condition dicts (e.g., [{"type": "Approved"}])

    Returns:
        JSON string representing oc get csr -o json output
    """
    items = []
    for csr in csrs_list:
        item = {
            "apiVersion": "certificates.k8s.io/v1",
            "kind": "CertificateSigningRequest",
            "metadata": {"name": csr["name"]},
            "spec": {"username": csr["username"]},
            "status": {"conditions": csr.get("conditions", [])},
        }
        items.append(item)

    return json.dumps({"apiVersion": "v1", "kind": "List", "items": items})


class TestNodeCertificateExpiry(RuleTestBase):
    """Test NodeCertificateExpiry validator."""

    tested_type = NodeCertificateExpiry

    # etcd certificate path for testing
    cert_path = "/etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-master-0.crt"

    # Generate dates for testing
    now = datetime.now()
    expired_date = (now - timedelta(days=30)).strftime("%b %d %H:%M:%S %Y")
    expiring_soon_date = (now + timedelta(days=20)).strftime("%b %d %H:%M:%S %Y")
    valid_date = (now + timedelta(days=365)).strftime("%b %d %H:%M:%S %Y")

    # Command outputs
    which_openssl = "which openssl"

    # Mock all glob expansion commands for CERT_PATHS
    glob_expansion_commands = {
        "ls /etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-*.crt 2>/dev/null": CmdOutput(
            out="/etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-master-0.crt",
            return_code=0,
        ),
        "ls /etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-peer-*.crt 2>/dev/null": CmdOutput(
            out="", return_code=1
        ),  # Not found
    }

    # Mock file existence checks (used by file_utils.is_file_exist)
    # Only etcd-serving certificate exists in our test scenario
    file_existence_commands = {
        "ls /etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-master-0.crt": CmdOutput(
            out="/etc/kubernetes/static-pod-resources/etcd-certs/secrets/etcd-all-certs/etcd-serving-master-0.crt",
            return_code=0,
        ),
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


class TestKubeletCsrHealthCheck(RuleTestBase):
    """Test KubeletCsrHealthCheck rule."""

    tested_type = KubeletCsrHealthCheck

    # All CSRs approved - healthy state
    csr_output_all_approved = _make_csr_json([
        {
            "name": "csr-node-worker-1",
            "username": "system:node:worker-1",
            "conditions": [{"type": "Approved"}],
        },
        {
            "name": "csr-node-worker-2",
            "username": "system:node:worker-2",
            "conditions": [{"type": "Approved"}],
        },
    ])

    # Some CSRs pending
    csr_output_pending = _make_csr_json([
        {
            "name": "csr-node-worker-1",
            "username": "system:node:worker-1",
            "conditions": [{"type": "Approved"}],
        },
        {
            "name": "csr-node-worker-2-pending",
            "username": "system:node:worker-2",
            "conditions": [],  # No conditions means Pending
        },
        {
            "name": "csr-node-worker-3-pending",
            "username": "system:node:worker-3",
            # No status field means Pending
        },
    ])

    # Some CSRs denied
    csr_output_denied = _make_csr_json([
        {
            "name": "csr-node-worker-1",
            "username": "system:node:worker-1",
            "conditions": [{"type": "Approved"}],
        },
        {
            "name": "csr-node-worker-2-denied",
            "username": "system:node:worker-2",
            "conditions": [{"type": "Denied"}],
        },
    ])

    # Mixed: pending and denied
    csr_output_mixed = _make_csr_json([
        {
            "name": "csr-node-worker-1",
            "username": "system:node:worker-1",
            "conditions": [{"type": "Approved"}],
        },
        {
            "name": "csr-node-worker-2-pending",
            "username": "system:node:worker-2",
            "conditions": [],
        },
        {
            "name": "csr-node-worker-3-denied",
            "username": "system:node:worker-3",
            "conditions": [{"type": "Denied"}],
        },
    ])

    # Non-kubelet CSRs should be ignored
    csr_output_non_kubelet = _make_csr_json([
        {
            "name": "csr-user-admin",
            "username": "admin",
            "conditions": [],  # Pending but not a kubelet CSR
        },
        {
            "name": "csr-serviceaccount-pending",
            "username": "system:serviceaccount:default:myapp",
            "conditions": [],  # Pending but not a kubelet CSR
        },
    ])

    # Empty CSR list
    csr_output_empty = json.dumps({"apiVersion": "v1", "kind": "List", "items": []})

    oc_cmd_key = ("get", ("csr", "-o", "json"))

    scenario_passed = [
        RuleScenarioParams(
            "all kubelet CSRs approved",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_all_approved)},
        ),
        RuleScenarioParams(
            "no CSRs in cluster",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_empty)},
        ),
        RuleScenarioParams(
            "only non-kubelet CSRs pending (should be ignored)",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_non_kubelet)},
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "kubelet CSRs pending",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_pending)},
            failed_msg=(
                "WARNING: 2 kubelet CSR(s) are PENDING approval:\n"
                "  csr-node-worker-2-pending\n"
                "  csr-node-worker-3-pending\n\n"
                "Pending CSRs indicate the 30-day automatic rotation mechanism is not working.\n"
                "Certificates will expire if CSRs remain pending."
            ),
        ),
        RuleScenarioParams(
            "kubelet CSR denied",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_denied)},
            failed_msg=(
                "CRITICAL: 1 kubelet CSR(s) have been DENIED:\n"
                "  csr-node-worker-2-denied\n\n"
                "Denied CSRs indicate certificate rotation was explicitly rejected.\n"
                "Kubelet certificates will NOT rotate automatically."
            ),
        ),
        RuleScenarioParams(
            "mixed pending and denied CSRs",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput(csr_output_mixed)},
            failed_msg=(
                "CRITICAL: 1 kubelet CSR(s) have been DENIED:\n"
                "  csr-node-worker-3-denied\n\n"
                "Denied CSRs indicate certificate rotation was explicitly rejected.\n"
                "Kubelet certificates will NOT rotate automatically.\n\n"
                "WARNING: 1 kubelet CSR(s) are PENDING approval:\n"
                "  csr-node-worker-2-pending\n\n"
                "Pending CSRs indicate the 30-day automatic rotation mechanism is not working.\n"
                "Certificates will expire if CSRs remain pending."
            ),
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "failed to get CSRs",
            oc_cmd_output_dict={oc_cmd_key: CmdOutput("error", return_code=1)},
            failed_msg="Failed to retrieve Certificate Signing Requests from cluster",
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
