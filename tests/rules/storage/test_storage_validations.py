"""
Tests for storage validations.

Ported from legacy test patterns to RuleTestBase pattern.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.rules.storage.storage_validations import (
    CephOsdTreeWorks,
    CephSlowOps,
    CheckPoolSize,
    IsCephHealthOk,
    IsCephOSDsNearFull,
    IsOSDsUp,
    IsOSDsWeightOK,
    OrphanCsiVolumes,
    OsdJournalError,
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
            },
            failed_msg="ceph osd tree is not working.\nError: connection refused",
        )
    ]

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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
            },
            failed_msg="Failed to get ceph health status.\nError: connection timeout",
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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

    scenario_passed = [
        RuleScenarioParams(
            "all OSDs are up",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_all_up, return_code=0
                )
            },
            tested_object_mock_dict={
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
            },
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "some OSDs are down",
            rsh_cmd_output_dict={
                ("openshift-storage", "rook-ceph-tools-12345", "ceph osd tree -f json"): CmdOutput(
                    out=osd_tree_some_down, return_code=0
                )
            },
            tested_object_mock_dict={
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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

    scenario_passed = [
        RuleScenarioParams(
            "no orphaned volumes",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123 csi-vol-def456"
                ),
            },
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-abc123"}, {"name": "csi-vol-def456"}]'),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
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
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("[]"),  # Won't be reached but needed for mock
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
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
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("NOT A JSON"),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
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
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-abc123"}, {"name": "csi-vol-orphan"}]'),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
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
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput(
                    '[{"name": "csi-vol-abc123"}, {"name": "csi-vol-orphan1"}, {"name": "csi-vol-orphan2"}]'
                ),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
            },
        ),
        RuleScenarioParams(
            "all volumes are orphans - no PVs",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(""),
            },
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput('[{"name": "csi-vol-orphan1"}, {"name": "csi-vol-orphan2"}]'),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
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
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput("", return_code=1, err="Error: unable to connect to ceph cluster"),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
            },
            failed_msg="Failed to list CSI subvolumes from Ceph.\nError: Error: unable to connect to ceph cluster",
        ),
        RuleScenarioParams(
            "ceph empty output",
            oc_cmd_output_dict={
                ("get", ("pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}")): CmdOutput(
                    "csi-vol-abc123"
                ),
            },
            rsh_cmd_output_dict={
                (
                    "openshift-storage",
                    "rook-ceph-tools-xyz",
                    "ceph fs subvolume ls ocs-storagecluster-cephfilesystem csi -f json",
                ): CmdOutput(""),
            },
            tested_object_mock_dict={
                "_get_ceph_pod": Mock(return_value=("openshift-storage", "rook-ceph-tools-xyz", "")),
            },
            failed_msg="Empty results from ceph fs subvolume ls command",
        ),
    ]

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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Pending", ready=False, restarts=0),
                    ]
                ),
                "run_oc_command": Mock(return_value=(0, "pod logs here", "")),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "run_oc_command": Mock(return_value=(0, "pod logs here", "")),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
                "_get_osd_pods": Mock(
                    return_value=[
                        create_pod_mock("rook-ceph-osd-0", phase="Running", ready=False, waiting_reason="CrashLoopBackOff"),
                    ]
                ),
                "run_oc_command": Mock(return_value=(0, "pod logs here", "")),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
                "_get_pod_name": Mock(return_value="rook-ceph-tools-12345"),
                "_select_resources": Mock(return_value=Mock()),
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
