"""Tests for etcd validations."""

import pytest

from in_cluster_checks.rules.etcd.etcd_validations import (
    EtcdAlarmCheck,
    EtcdBackendCommitPerformanceCheck,
    EtcdBasicCheck,
    EtcdEndpointHealthCheck,
    EtcdLeaderCheck,
    EtcdMemberCountCheck,
    EtcdWalFsyncPerformanceCheck,
    EtcdWriteReadCycleCheck,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


# EtcdBasicCheck Tests


class TestEtcdBasicCheck(RuleTestBase):
    tested_type = EtcdBasicCheck

    scenario_passed = [
        RuleScenarioParams(
            "etcd version command succeeds",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl version"): CmdOutput(
                    "etcdctl version: 3.5.6\nAPI version: 3.5"
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "etcd not reachable",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl version"): CmdOutput(
                    "", return_code=1, err="Error: connection refused"
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Could not connect to etcd. Command failed with rc=1\nError: Error: connection refused",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdAlarmCheck Tests


class TestEtcdAlarmCheck(RuleTestBase):
    tested_type = EtcdAlarmCheck

    scenario_passed = [
        RuleScenarioParams(
            "no alarms present",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl alarm list"): CmdOutput(""),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "alarms present",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl alarm list"): CmdOutput(
                    "memberID:1234567890 alarm:NOSPACE\nmemberID:9876543210 alarm:NOSPACE"
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Etcd has active alarms:\nmemberID:1234567890 alarm:NOSPACE\nmemberID:9876543210 alarm:NOSPACE",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdMemberCountCheck Tests


class TestEtcdMemberCountCheck(RuleTestBase):
    tested_type = EtcdMemberCountCheck

    scenario_passed = [
        RuleScenarioParams(
            "3 members exist",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "id": "123"}, {"name": "master-1", "id": "456"}, {"name": "master-2", "id": "789"}]}'
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "less than 3 members",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "id": "123"}, {"name": "master-1", "id": "456"}]}'
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Etcd does not have at least three members (found 2): master-0, master-1",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdLeaderCheck Tests


class TestEtcdLeaderCheck(RuleTestBase):
    tested_type = EtcdLeaderCheck

    leader_present_output = """[
        {"Endpoint": "https://10.0.0.1:2379", "Status": {"leader": 2}},
        {"Endpoint": "https://10.0.0.2:2379", "Status": {"leader": 2}},
        {"Endpoint": "https://10.0.0.3:2379", "Status": {"leader": 0}}
    ]"""

    no_leader_output = """[
        {"Endpoint": "https://10.0.0.1:2379", "Status": {"leader": 0}},
        {"Endpoint": "https://10.0.0.2:2379", "Status": {"leader": 0}},
        {"Endpoint": "https://10.0.0.3:2379", "Status": {"leader": 0}}
    ]"""

    scenario_passed = [
        RuleScenarioParams(
            "leader exists",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl endpoint status -w=json"): CmdOutput(
                    leader_present_output
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "no leader",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl endpoint status -w=json"): CmdOutput(
                    no_leader_output
                ),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Etcd does not have a leader",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdEndpointHealthCheck Tests


class TestEtcdEndpointHealthCheck(RuleTestBase):
    tested_type = EtcdEndpointHealthCheck

    scenario_passed = [
        RuleScenarioParams(
            "all endpoints healthy",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}, {"name": "master-1", "clientURLs": ["https://10.0.0.2:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/health",
                ): CmdOutput('{"health": "true"}'),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.2:2379/health",
                ): CmdOutput('{"health": "true"}'),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "unhealthy endpoint",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}, {"name": "master-1", "clientURLs": ["https://10.0.0.2:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/health",
                ): CmdOutput('{"health": "true"}'),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.2:2379/health",
                ): CmdOutput('{"health": "false"}'),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg='The following etcd endpoints are not healthy: [\'https://10.0.0.2:2379\']\nhttps://10.0.0.1:2379: {"health": "true"}\nhttps://10.0.0.2:2379: {"health": "false"}',
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdWriteReadCycleCheck Tests


class TestEtcdWriteReadCycleCheck(RuleTestBase):
    tested_type = EtcdWriteReadCycleCheck

    test_key = "52093047-521a-4039-baee-429e1779c268"
    test_value = "40c774ad-35e4-46c5-bcd3-e1ff2b95fb67"

    scenario_passed = [
        RuleScenarioParams(
            "write/read cycle succeeds",
            rsh_cmd_output_dict={
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    f"etcdctl put {test_key} {test_value}",
                ): CmdOutput("OK"),
                ("openshift-etcd", "etcd-master-0", f"etcdctl get {test_key}"): CmdOutput(
                    f"{test_key}\n{test_value}"
                ),
                ("openshift-etcd", "etcd-master-0", f"etcdctl del {test_key}"): CmdOutput("1"),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "write fails",
            rsh_cmd_output_dict={
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    f"etcdctl put {test_key} {test_value}",
                ): CmdOutput("", return_code=1, err="Error: write failed"),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Failed to write test data to etcd (rc=1)\nError: Error: write failed",
        ),
        RuleScenarioParams(
            "value mismatch",
            rsh_cmd_output_dict={
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    f"etcdctl put {test_key} {test_value}",
                ): CmdOutput("OK"),
                ("openshift-etcd", "etcd-master-0", f"etcdctl get {test_key}"): CmdOutput(
                    f"{test_key}\nwrong-value"
                ),
                ("openshift-etcd", "etcd-master-0", f"etcdctl del {test_key}"): CmdOutput("1"),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg=f"Read value 'wrong-value' does not match written value '{test_value}'",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


# EtcdWalFsyncPerformanceCheck Tests


class TestEtcdWalFsyncPerformanceCheck(RuleTestBase):
    tested_type = EtcdWalFsyncPerformanceCheck

    # Metrics with 0.5% slow (under 1% threshold)
    good_metrics = """etcd_disk_wal_fsync_duration_seconds_bucket{le="0.008"} 9950.0
etcd_disk_wal_fsync_duration_seconds_bucket{le="+Inf"} 10000.0
etcd_disk_wal_fsync_duration_seconds_count 10000.0"""

    # Metrics with 5% slow (over 1% threshold)
    slow_metrics = """etcd_disk_wal_fsync_duration_seconds_bucket{le="0.008"} 9500.0
etcd_disk_wal_fsync_duration_seconds_bucket{le="+Inf"} 10000.0
etcd_disk_wal_fsync_duration_seconds_count 10000.0"""

    scenario_passed = [
        RuleScenarioParams(
            "good performance",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/metrics | grep etcd_disk_wal_fsync_duration_seconds",
                ): CmdOutput(good_metrics),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "slow performance",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/metrics | grep etcd_disk_wal_fsync_duration_seconds",
                ): CmdOutput(slow_metrics),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Etcd WAL fsync performance is slow on 1 endpoint(s):\n  - https://10.0.0.1:2379: 5.00% of fsync operations exceed 8ms threshold",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)


# EtcdBackendCommitPerformanceCheck Tests


class TestEtcdBackendCommitPerformanceCheck(RuleTestBase):
    tested_type = EtcdBackendCommitPerformanceCheck

    # Metrics with 0.5% slow (under 1% threshold)
    good_metrics = """etcd_disk_backend_commit_duration_seconds_bucket{le="0.032"} 9950.0
etcd_disk_backend_commit_duration_seconds_bucket{le="+Inf"} 10000.0
etcd_disk_backend_commit_duration_seconds_count 10000.0"""

    # Metrics with 3% slow (over 1% threshold)
    slow_metrics = """etcd_disk_backend_commit_duration_seconds_bucket{le="0.032"} 9700.0
etcd_disk_backend_commit_duration_seconds_bucket{le="+Inf"} 10000.0
etcd_disk_backend_commit_duration_seconds_count 10000.0"""

    scenario_passed = [
        RuleScenarioParams(
            "good performance",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/metrics | grep etcd_disk_backend_commit_duration_seconds",
                ): CmdOutput(good_metrics),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "slow performance",
            rsh_cmd_output_dict={
                ("openshift-etcd", "etcd-master-0", "etcdctl member list -w=json"): CmdOutput(
                    '{"members": [{"name": "master-0", "clientURLs": ["https://10.0.0.1:2379"]}]}'
                ),
                (
                    "openshift-etcd",
                    "etcd-master-0",
                    "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET https://10.0.0.1:2379/metrics | grep etcd_disk_backend_commit_duration_seconds",
                ): CmdOutput(slow_metrics),
            },
            tested_object_mock_dict={
                "_get_pod_name": lambda ns, labels: "etcd-master-0",
            },
            failed_msg="Etcd backend commit performance is slow on 1 endpoint(s):\n  - https://10.0.0.1:2379: 3.00% of commits exceed 32ms threshold",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)
