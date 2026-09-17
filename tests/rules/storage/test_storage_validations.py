"""
Tests for storage validations.

Ported from legacy test patterns to RuleTestBase pattern.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.rules.storage.storage_validations import (
    CephAccessRule,
    CephOsdTreeWorks,
    CephSlowOps,
    CheckPoolSize,
    InternalCephRule,
    IsCephHealthOk,
    IsCephOSDsNearFull,
    IsOSDsUp,
    IsOSDsWeightOK,
    OrphanCsiVolumes,
    OsdJournalError,
    OsdPrepareFilesystemHealth,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


def create_pod_mock(
    name, phase="Running", ready=True, restarts=0, last_restart=None, waiting_reason=None, terminated_reason=None
):
    """Create a mock pod object for testing."""
    mock_pod = Mock()

    # Container state
    container_state = Mock()
    container_state.running = Mock() if phase == "Running" and not waiting_reason and not terminated_reason else None
    container_state.waiting = Mock(reason=waiting_reason, message="") if waiting_reason else None
    container_state.terminated = Mock(reason=terminated_reason, message="") if terminated_reason else None

    # Container status
    container_status = Mock()
    container_status.name = name
    container_status.ready = ready
    container_status.restartCount = restarts  # camelCase!
    container_status.state = container_state

    if last_restart:
        last_state = Mock()
        last_state.terminated = Mock(finishedAt=last_restart)  # camelCase!
        container_status.lastState = last_state  # camelCase!
    else:
        container_status.lastState = Mock(terminated=None)  # camelCase!

    # Pod model with status and metadata
    mock_pod.model.status.phase = phase
    mock_pod.model.status.containerStatuses = [container_status]  # camelCase!
    mock_pod.model.metadata.labels = {"ceph-osd-id": name.split("-")[-1]} if "osd" in name else {}

    # Pod name() method
    mock_pod.name.return_value = name

    return mock_pod


class TestCephOsdTreeWorks(RuleTestBase):
    """Test CephOsdTreeWorks rule."""

    tested_type = CephOsdTreeWorks

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no operator pod available",
            tested_object_mock_dict={
                # Both tools and operator pods return None
                "oc_api.get_pod_name": Mock(return_value=None),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "external ceph mode without tools pod (CephAccessRule check)",
            tested_object_mock_dict={
                # Operator found, no OSD pods (external mode), no tools pod
                "oc_api.get_pod_name": Mock(side_effect=["rook-ceph-operator-abc123", None, None]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "operator pod available",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-operator-abc123"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_passed = [
        RuleScenarioParams(
            "ceph osd tree command succeeds",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree"): CmdOutput(
                    out="ID CLASS WEIGHT  TYPE NAME       STATUS REWEIGHT PRI-AFF\n-1       1.00000 root default",
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "ceph osd tree via operator pod (tools pod not available)",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-operator-abc123", "ceph osd tree -c /var/lib/rook/openshift-storage/openshift-storage.config"): CmdOutput(
                    out="ID CLASS WEIGHT  TYPE NAME       STATUS REWEIGHT PRI-AFF\n-1       1.00000 root default",
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                # First call returns None (no tools pod), second call returns operator pod
                "oc_api.get_pod_name": Mock(side_effect=[None, "rook-ceph-operator-abc123"]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph osd tree command fails",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree"): CmdOutput(
                    out="", err="connection refused", return_code=1
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="ceph osd tree is not working.\nError: connection refused",
        ),
        RuleScenarioParams(
            "ceph osd tree via operator pod fails",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-operator-abc123", "ceph osd tree -c /var/lib/rook/openshift-storage/openshift-storage.config"): CmdOutput(
                    out="", err="failed to connect", return_code=1
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(side_effect=[None, "rook-ceph-operator-abc123"]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="ceph osd tree is not working.\nError: failed to connect",
        )
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestIsCephHealthOk(RuleTestBase):
    """Test IsCephHealthOk rule."""

    tested_type = IsCephHealthOk

    health_ok_json = """{"status": "HEALTH_OK", "checks": {}, "mutes": []}"""

    health_ok_old_format = """{"overall_status": "HEALTH_OK", "summary": [], "detail": []}"""

    health_warn_with_checks = """{
        "status": "HEALTH_WARN",
        "checks": {
            "MON_DOWN": {
                "severity": "HEALTH_WARN",
                "summary": {
                    "message": "1/3 mons down, quorum a,b"
                }
            },
            "OSD_DOWN": {
                "severity": "HEALTH_WARN",
                "summary": {
                    "message": "2 osds down"
                }
            }
        },
        "mutes": []
    }"""

    health_err_with_summary = """{
        "overall_status": "HEALTH_ERR",
        "summary": [
            {"severity": "HEALTH_ERR", "summary": "1 MDSs are laggy"},
            {"severity": "HEALTH_WARN", "summary": "pool data has too few pgs"}
        ],
        "detail": []
    }"""

    scenario_passed = [
        RuleScenarioParams(
            "ceph health is ok (new format)",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-12345",
                    "ceph health -f json",
                ): CmdOutput(out=health_ok_json, return_code=0)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "ceph health is ok (old format)",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-12345",
                    "ceph health -f json",
                ): CmdOutput(out=health_ok_old_format, return_code=0)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "ceph health via operator pod (tools pod not available)",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-operator-abc123",
                    "ceph health -f json -c /var/lib/rook/openshift-storage/openshift-storage.config",
                ): CmdOutput(out=health_ok_json, return_code=0)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(side_effect=[None, "rook-ceph-operator-abc123"]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph health warning with checks",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-12345",
                    "ceph health -f json",
                ): CmdOutput(out=health_warn_with_checks, return_code=0)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "Ceph health is not ok.\n"
                "{\n"
                '    "MON_DOWN": {\n'
                '        "severity": "HEALTH_WARN",\n'
                '        "message": "1/3 mons down, quorum a,b"\n'
                "    },\n"
                '    "OSD_DOWN": {\n'
                '        "severity": "HEALTH_WARN",\n'
                '        "message": "2 osds down"\n'
                "    }\n"
                "}"
            ),
        ),
        RuleScenarioParams(
            "ceph health error with summary",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-12345",
                    "ceph health -f json",
                ): CmdOutput(out=health_err_with_summary, return_code=0)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "Ceph health is not ok.\n"
                "{\n"
                '    "1 MDSs are laggy": {\n'
                '        "severity": "HEALTH_ERR"\n'
                "    },\n"
                '    "pool data has too few pgs": {\n'
                '        "severity": "HEALTH_WARN"\n'
                "    }\n"
                "}"
            ),
        ),
        RuleScenarioParams(
            "ceph health command failed",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-12345",
                    "ceph health -f json",
                ): CmdOutput(out="", err="connection timeout", return_code=1)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph health status.\nError: connection timeout",
        ),
        RuleScenarioParams(
            "ceph health via operator pod fails",
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-operator-abc123",
                    "ceph health -f json -c /var/lib/rook/openshift-storage/openshift-storage.config",
                ): CmdOutput(out="", err="cluster unreachable", return_code=1)
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(side_effect=[None, "rook-ceph-operator-abc123"]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph health status.\nError: cluster unreachable",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestIsCephOSDsNearFull(RuleTestBase):
    """Test IsCephOSDsNearFull rule."""

    tested_type = IsCephOSDsNearFull

    df_output_ok = """{
        "stats": {"total_bytes": 1099511627776, "total_used_bytes": 107374182400},
        "nodes": [
            {"id": 0, "name": "osd.0", "kb_used": 10485760, "kb": 104857600, "pgs": 100, "utilization": 10.0},
            {"id": 1, "name": "osd.1", "kb_used": 10485760, "kb": 104857600, "pgs": 100, "utilization": 10.0}
        ]
    }"""

    df_output_warning = """{
        "stats": {"total_bytes": 1099511627776, "total_used_bytes": 879609302221},
        "nodes": [
            {"id": 0, "name": "osd.0", "kb_used": 85983641, "kb": 104857600, "pgs": 100, "utilization": 82.0},
            {"id": 1, "name": "osd.1", "kb_used": 10485760, "kb": 104857600, "pgs": 100, "utilization": 10.0}
        ]
    }"""

    df_output_critical = """{
        "stats": {"total_bytes": 1099511627776, "total_used_bytes": 989560463777},
        "nodes": [
            {"id": 0, "name": "osd.0", "kb_used": 96703897, "kb": 104857600, "pgs": 100, "utilization": 92.2},
            {"id": 1, "name": "osd.1", "kb_used": 10485760, "kb": 104857600, "pgs": 100, "utilization": 10.0}
        ]
    }"""

    scenario_passed = [
        RuleScenarioParams(
            "all OSDs within limits",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=df_output_ok, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "OSD near full (warning threshold)",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=df_output_warning, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "There are OSDs disk usage near or already over the limit.\n"
                "This indicates there is a risk ahead or already materialized, so need to react fast for ceph storage.\n"
                "Here is a list of problematic OSDs in this environment currently over limit:\n\n"
                "Threshold: 80% (WARNING)\n\n"
                "OSD Name        Utilization    \n"
                "------------------------------\n"
                "osd.0           82.00          %\n"
            ),
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "OSD near full (critical threshold)",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=df_output_critical, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "There are OSDs disk usage near or already over the limit.\n"
                "This indicates there is a risk ahead or already materialized, so need to react fast for ceph storage.\n"
                "Here is a list of problematic OSDs in this environment currently over limit:\n\n"
                "Threshold: 90% (CRITICAL)\n\n"
                "OSD Name        Utilization    \n"
                "------------------------------\n"
                "osd.0           92.20          %\n"
            ),
        ),
        RuleScenarioParams(
            "ceph osd df command failed",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out="", err="command not found", return_code=127
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph osd df status.\nError: command not found",
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


class TestIsOSDsUp(RuleTestBase):
    """Test IsOSDsUp rule."""

    tested_type = IsOSDsUp

    osd_tree_all_up = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "type": "osd", "status": "up"},
            {"id": 1, "name": "osd.1", "type": "osd", "status": "up"},
            {"id": -1, "name": "default", "type": "root"}
        ]
    }"""

    osd_tree_some_down = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "type": "osd", "status": "up"},
            {"id": 1, "name": "osd.1", "type": "osd", "status": "down"},
            {"id": 2, "name": "osd.2", "type": "osd", "status": "down"},
            {"id": -1, "name": "default", "type": "root"}
        ]
    }"""

    osd_tree_no_nodes = '{"nodes": []}'
    osd_tree_invalid_nodes = '{"nodes": ["invalid"]}'

    scenario_passed = [
        RuleScenarioParams(
            "all OSDs are up",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph osd tree output is empty",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out="", return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Empty results from ceph osd tree command",
        ),
        RuleScenarioParams(
            "ceph osd tree output has no nodes",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_no_nodes, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="No nodes found in ceph osd tree output",
        ),
        RuleScenarioParams(
            "ceph osd tree output has malformed nodes",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_invalid_nodes, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Invalid results from ceph osd tree command",
        ),
        RuleScenarioParams(
            "some OSDs are down",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_some_down, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="The following OSDs are in down state: [osd.1, osd.2]",
        ),
        RuleScenarioParams(
            "ceph osd tree command failed",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out="", err="ceph cluster not available", return_code=1
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph osd tree status.\nError: ceph cluster not available",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize(
        "scenario_params",
        [
            RuleScenarioParams(
                "ceph osd tree output is malformed",
                rsh_cmd_output_dict={
                    ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                        out="not-json", return_code=0
                    )
                },
                tested_object_mock_dict={
                    "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                    "oc_api.select_single_resource": Mock(return_value=Mock()),
                },
            )
        ],
    )
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)


class TestIsOSDsWeightOK(RuleTestBase):
    """Test IsOSDsWeightOK rule."""

    tested_type = IsOSDsWeightOK

    osd_df_weights_ok = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "crush_weight": 1.0, "kb": 1073741824},
            {"id": 1, "name": "osd.1", "crush_weight": 1.0, "kb": 1073741824}
        ]
    }"""

    osd_df_weight_too_high = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "crush_weight": 1.5, "kb": 1073741824},
            {"id": 1, "name": "osd.1", "crush_weight": 1.0, "kb": 1073741824}
        ]
    }"""

    osd_df_weight_too_low = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "crush_weight": 0.5, "kb": 1073741824},
            {"id": 1, "name": "osd.1", "crush_weight": 1.0, "kb": 1073741824}
        ]
    }"""

    scenario_passed = [
        RuleScenarioParams(
            "all OSD weights are correct",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=osd_df_weights_ok, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "OSD weight too high",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=osd_df_weight_too_high, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "The following OSDs weight not in acceptable range:\n\n"
                "OSD '0' - current weight is 1.5, while it should be greater than 0.95 and smaller than 1.05"
            ),
        ),
        RuleScenarioParams(
            "OSD weight too low",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out=osd_df_weight_too_low, return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "The following OSDs weight not in acceptable range:\n\n"
                "OSD '0' - current weight is 0.5, while it should be greater than 0.95 and smaller than 1.05"
            ),
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph osd df command failed",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd df -f json"): CmdOutput(
                    out="", err="timeout", return_code=124
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph osd df status.\nError: timeout",
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


class TestOrphanCsiVolumes(RuleTestBase):
    """Tests for OrphanCsiVolumes rule."""

    tested_type = OrphanCsiVolumes

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "cephfs filesystem not found",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "other-filesystem"}]', return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "csi subvolume group does not exist",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "other-group"}]', return_code=0),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "cannot query ceph filesystems",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out="", err="connection refused", return_code=1
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "cannot query subvolume groups",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out="", err="timeout", return_code=1),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "cephfs and csi subvolume group exist",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_passed = [
        RuleScenarioParams(
            "no orphaned volumes",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123 csi-vol-def456"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-abc123"}, {"name": "csi-vol-def456"}]'),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "no subvolumes exist yet - empty result",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(""),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("[]"),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "subvolume group exists but ENOENT error - graceful fallback",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(""),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput(
                    "", return_code=2, err="Error ENOENT: subvolume group 'csi' does not exist"
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "oc get pv command failed",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "", return_code=1, err="Unable to connect to the server"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("[]"),  # Won't be reached but needed for mock
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "ceph invalid json",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("NOT A JSON"),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "single orphaned volume",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-abc123"}, {"name": "csi-vol-orphan"}]'),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "multiple orphaned volumes",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput(
                    '[{"name": "csi-vol-abc123"}, {"name": "csi-vol-orphan1"}, {"name": "csi-vol-orphan2"}]'
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "all volumes are orphans - no PVs",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(""),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-orphan1"}, {"name": "csi-vol-orphan2"}]'),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
        RuleScenarioParams(
            "ceph command failed",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123"
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-xyz", "ceph fs ls -f json"): CmdOutput(
                    out='[{"name": "ocs-storagecluster-cephfilesystem"}]', return_code=0
                ),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolumegroup ls ocs-storagecluster-cephfilesystem -f json",
                ): CmdOutput(out='[{"name": "csi"}]', return_code=0),
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("", return_code=1, err="Error: unable to connect to ceph cluster"),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-xyz"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to list CSI subvolumes from Ceph.\nError: Error: unable to connect to ceph cluster",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)

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
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestCheckPoolSize(RuleTestBase):

    tested_type = CheckPoolSize

    scenario_passed = [
        RuleScenarioParams(
            "all pools have replication factor >= 2",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd pool ls detail -f json"): CmdOutput(
                    out='[{"size": 2, "pool_name": "name1"}]',
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "pool has replication factor less than 2",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd pool ls detail -f json"): CmdOutput(
                    out='[{"size": 2, "pool_name": "name1"}, {"size": 1, "pool_name": "name2"}]',
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="ceph replication factor is less than 2 in following pools:\nname2",
        ),
        RuleScenarioParams(
            "multiple pools have replication factor less than 2",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd pool ls detail -f json"): CmdOutput(
                    out='[{"size": 1, "pool_name": "pool1"}, {"size": 1, "pool_name": "pool2"}, {"size": 3, "pool_name": "pool3"}]',
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="ceph replication factor is less than 2 in following pools:\npool1\npool2",
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph command failed",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd pool ls detail -f json"): CmdOutput(
                    out="", err="connection refused", return_code=1
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph pool details.\nError: connection refused",
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


def _create_prepare_pod_mock(name, phase="Succeeded"):
    """Create a mock OSD prepare pod with metadata provided by Rook."""
    mock_pod = Mock()
    mock_pod.name.return_value = name
    mock_pod.model.metadata.labels = {"app": "rook-ceph-osd-prepare"}
    mock_pod.model.status.phase = phase
    return mock_pod


# Device UUID used in prepare pod names for test scenarios
_DEVICE_UUID_A = "a888f0a01744fafe59f31ebb9e271afa"
_DEVICE_UUID_B = "b999e1b12855fbfe6a42ecba0e382bfb"
_DEVICE_UUID_C = "cccc22c33366dddd77778888aaaabbbb"

# bluestore_bdev_uuid format (hyphenated) corresponding to _DEVICE_UUID_A
_BDEV_UUID_A = "a888f0a0-1744-fafe-59f3-1ebb9e271afa"
_BDEV_UUID_B = "b999e1b1-2855-fbfe-6a42-ecba0e382bfb"


class TestOsdPrepareFilesystemHealth(RuleTestBase):
    """Test OsdPrepareFilesystemHealth rule."""

    tested_type = OsdPrepareFilesystemHealth

    prepare_log_with_error = (
        "2024-03-15T10:30:00.123 I | cephosd: starting OSD prepare\n"
        "2024-03-15T10:30:01.456 I | cephosd: skipping device /dev/sdb because it contains a filesystem\n"
        "2024-03-15T10:30:02.789 I | cephosd: completed OSD prepare"
    )

    prepare_log_clean = (
        "2024-03-15T10:30:00.123 I | cephosd: starting OSD prepare\n"
        "2024-03-15T10:30:01.456 I | cephosd: OSD prepare completed successfully"
    )

    osd_tree_all_up = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "type": "osd", "status": "up"},
            {"id": 1, "name": "osd.1", "type": "osd", "status": "up"},
            {"id": -1, "name": "default", "type": "root"}
        ]
    }"""

    osd_tree_osd1_down = """{
        "nodes": [
            {"id": 0, "name": "osd.0", "type": "osd", "status": "up"},
            {"id": 1, "name": "osd.1", "type": "osd", "status": "down"},
            {"id": -1, "name": "default", "type": "root"}
        ]
    }"""

    osd_metadata_json = json.dumps([
        {"id": 0, "bluestore_bdev_uuid": _BDEV_UUID_A},
        {"id": 1, "bluestore_bdev_uuid": _BDEV_UUID_B},
    ])

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "no OSD prepare pods found",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(return_value=[]),
            },
        ),
        RuleScenarioParams(
            "external ceph mode detected (InternalCephRule check)",
            tested_object_mock_dict={
                # Operator found, no OSD pods (external mode)
                "oc_api.get_pod_name": Mock(side_effect=["rook-ceph-operator-abc123", None]),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "OSD prepare pods exist",
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
        ),
    ]

    _REMEDIATION = (
        "\nRemediation: Investigate why OSD provisioning is failing. "
        "Before any cleanup, verify the affected device is not in use by an active OSD. "
        "See https://access.redhat.com/solutions/6910101"
    )

    _LOG_LINE = (
        "2024-03-15T10:30:01.456 I | cephosd: skipping device /dev/sdb because it contains a filesystem"
    )

    scenario_passed = [
        RuleScenarioParams(
            "OSD prepare pods with clean logs (no filesystem errors)",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_clean
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "completed pod with OSD up - historical (no active failure)",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "filesystem error on succeeded pod with unrelated down OSD (UUID does not match down OSD)",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_osd1_down, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
        ),
        RuleScenarioParams(
            "no UUID in pod name and pod is not Failed (historical)",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", "rook-ceph-osd-prepare-node1", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_osd1_down, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[_create_prepare_pod_mock("rook-ceph-osd-prepare-node1")]
                ),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "OSD down fires - pod with filesystem error and corresponding OSD is down",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_osd1_down, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99")
                    ]
                ),
            },
            failed_msg=(
                "OSD prepare pods with existing filesystem errors and correlated down OSDs:\n"
                f"  - rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99 (correlated OSD: osd.1)\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "Failed pod with no UUID in pod name",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", "rook-ceph-osd-prepare-node1", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[_create_prepare_pod_mock("rook-ceph-osd-prepare-node1", "Failed")]
                ),
            },
            failed_msg=(
                "Failed OSD prepare pods with existing filesystem errors:\n"
                "  - rook-ceph-osd-prepare-node1\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "Failed pod with UUID not in ceph metadata",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_C}-zzz11", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_C}-zzz11", "Failed")
                    ]
                ),
            },
            failed_msg=(
                "Failed OSD prepare pods with existing filesystem errors:\n"
                f"  - rook-ceph-osd-prepare-{_DEVICE_UUID_C}-zzz11\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "Failed pod with UUID resolving to UP OSD",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "Failed")
                    ]
                ),
            },
            failed_msg=(
                "Failed OSD prepare pods with existing filesystem errors:\n"
                f"  - rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "Failed pod with resolvable UUID and Succeeded pod - both OSDs up",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12"),
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99", "Failed"),
                    ]
                ),
            },
            failed_msg=(
                "Failed OSD prepare pods with existing filesystem errors:\n"
                f"  - rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "combined - OSD down pod and Failed unresolvable pod both fire",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
                ("logs", ("-n", "openshift-storage", "rook-ceph-osd-prepare-node2", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_osd1_down, return_code=0
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99"),
                        _create_prepare_pod_mock("rook-ceph-osd-prepare-node2", "Failed"),
                    ]
                ),
            },
            failed_msg=(
                "Failed OSD prepare pods with existing filesystem errors:\n"
                "  - rook-ceph-osd-prepare-node2\n"
                f"    Log: {_LOG_LINE}\n"
                "\n"
                "OSD prepare pods with existing filesystem errors and correlated down OSDs:\n"
                f"  - rook-ceph-osd-prepare-{_DEVICE_UUID_B}-xyz99 (correlated OSD: osd.1)\n"
                f"    Log: {_LOG_LINE}\n"
                + _REMEDIATION
            ),
        ),
        RuleScenarioParams(
            "ceph osd metadata command fails",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out="", err="connection refused", return_code=1
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
            failed_msg="Failed to get ceph osd metadata.\nError: connection refused",
        ),
        RuleScenarioParams(
            "ceph osd tree command fails",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    prepare_log_with_error
                ),
            },
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd metadata -f json"): CmdOutput(
                    out=osd_metadata_json, return_code=0
                ),
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out="", err="connection refused", return_code=1
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
            failed_msg="Failed to get ceph osd tree status.\nError: connection refused",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "oc logs command fails for prepare pod",
            oc_cmd_output_dict={
                ("logs", ("-n", "openshift-storage", f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12", "--tail=50")): CmdOutput(
                    "", return_code=1, err="unable to retrieve container logs"
                ),
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
                "_get_osd_prepare_pods": Mock(
                    return_value=[
                        _create_prepare_pod_mock(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-abc12")
                    ]
                ),
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)

    def test_get_osd_prepare_pods_includes_succeeded(self, tested_object):
        """Verify collection does not exclude completed prepare pods."""
        tested_object.oc_api.get_pods = Mock(return_value=[])

        tested_object._get_osd_prepare_pods()

        tested_object.oc_api.get_pods.assert_called_once_with(
            namespace="openshift-storage", labels={"app": "rook-ceph-osd-prepare"}
        )

    def test_extract_device_uuid_valid_pod_name(self, tested_object):
        """Verify UUID extraction from standard prepare pod name format."""
        uuid = tested_object._extract_device_uuid(f"rook-ceph-osd-prepare-{_DEVICE_UUID_A}-t2fq8")
        assert uuid == _DEVICE_UUID_A

    def test_extract_device_uuid_no_match(self, tested_object):
        """Verify None returned for pod names without a valid UUID."""
        assert tested_object._extract_device_uuid("rook-ceph-osd-prepare-node1") is None
        assert tested_object._extract_device_uuid("rook-ceph-osd-0-abc12-xyz99") is None


class TestCephSlowOps(RuleTestBase):
    """Test CephSlowOps rule."""

    tested_type = CephSlowOps

    scenario_passed = [
        RuleScenarioParams(
            "no slow ops found",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph health detail"): CmdOutput(
                    out="HEALTH_OK", return_code=0
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "SLOW_OPS detected in health detail",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph health detail"): CmdOutput(
                    out=(
                        "HEALTH_WARN 30 slow requests are blocked > 32 sec\n"
                        "[WRN] SLOW_OPS: 30 slow requests are blocked > 32 sec"
                    ),
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "There are slow ops observed on this cluster. "
                "Blocked/Slow ops can have numerous possible root causes from bad media, "
                "cluster saturation and networking issues."
            ),
        ),
        RuleScenarioParams(
            "REQUEST_SLOW detected in health detail",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph health detail"): CmdOutput(
                    out="HEALTH_WARN REQUEST_SLOW: 5 ops are blocked",
                    return_code=0,
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg=(
                "There are slow ops observed on this cluster. "
                "Blocked/Slow ops can have numerous possible root causes from bad media, "
                "cluster saturation and networking issues."
            ),
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "ceph health detail command failed",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph health detail"): CmdOutput(
                    out="", err="connection refused", return_code=1
                )
            },
            tested_object_mock_dict={
                "oc_api.get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "oc_api.select_single_resource": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph health detail.\nError: connection refused",
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
