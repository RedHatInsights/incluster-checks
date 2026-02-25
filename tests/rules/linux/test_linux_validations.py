"""
Tests for Linux validations ported from support.

Adapted from healthcheck-backup/HealthChecks/tests/pytest/flows/Linux/test_linux_validations.py
"""

import pytest

from openshift_in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from openshift_in_cluster_checks.rules.linux.linux_validations import (
    AuditdBacklogLimit,
    SelinuxMode,
    SystemdServicesStatus,
    TooManyOpenFilesCheck,
    VerifyDuNotHang,
    YumlockFileCheck,
    ClockSynchronized,
    IsHostReachable,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


class TestSystemdServicesStatus(RuleTestBase):
    """Test SystemdServicesStatus validator."""

    tested_type = SystemdServicesStatus

    validation_cmd = "systemctl list-units | grep failed"

    failed_service_output = """● sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\x2dports-vport2p1.device loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1"""

    multiple_failed_services = """● sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\x2dports-vport2p1.device loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1
● some-other-service.service loaded failed failed Some Other Service"""

    harmless_service_output = """● systemd-network-generator.service loaded failed failed Network Manager Wait Online"""

    mixed_services_output = """● systemd-network-generator.service loaded failed failed Network Manager Wait Online
● sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\x2dports-vport2p1.device loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1"""

    scenario_passed = [
        RuleScenarioParams(
            "no failed services",
            {validation_cmd: CmdOutput(out="", return_code=1)},
        ),
        RuleScenarioParams(
            "only harmless services failed",
            {validation_cmd: CmdOutput(out=harmless_service_output, return_code=0)},
        ),
    ]

    scenario_warning = [
        RuleScenarioParams(
            "service failed (warning)",
            {validation_cmd: CmdOutput(out=failed_service_output, return_code=0)},
            failed_msg=(
                "The following services are in failed state:\n"
                "['sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\\\x2dports-vport2p1.device "
                "loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1']"
            ),
        ),
        RuleScenarioParams(
            "multiple services failed (warning)",
            {validation_cmd: CmdOutput(out=multiple_failed_services, return_code=0)},
            failed_msg=(
                "The following services are in failed state:\n"
                "['sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\\\x2dports-vport2p1.device "
                "loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1', "
                "'some-other-service.service loaded failed failed Some Other Service']"
            ),
        ),
        RuleScenarioParams(
            "mixed harmless and failed services (warning)",
            {validation_cmd: CmdOutput(out=mixed_services_output, return_code=0)},
            failed_msg=(
                "The following services are in failed state:\n"
                "['sys-devices-pci0000:00-0000:00:06.0-virtio2-virtio\\\\x2dports-vport2p1.device "
                "loaded failed failed /sys/devices/pci0000:00/0000:00:06.0/virtio2/virtio-ports/vport2p1']"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)


class TestIsHostReachable(RuleTestBase):
    """Test IsHostReachable validator."""

    tested_type = IsHostReachable

    validation_cmd = "echo 'regards to host'"

    scenario_passed = [
        RuleScenarioParams(
            "host is reachable",
            {validation_cmd: CmdOutput(out="regards to host", return_code=0)},
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "host not reachable",
            {validation_cmd: CmdOutput(out="", return_code=1)},
            failed_msg="host 192.168.1.10 not reachable",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestVerifyDuNotHang(RuleTestBase):
    """Test VerifyDuNotHang validator."""

    tested_type = VerifyDuNotHang

    # Note: add_bash_timeout=True wraps the command with "timeout --kill-after=60s 120s ..." (default timeout)
    validation_cmd = "timeout --kill-after=60s 120s du /tmp > /dev/null 2>&1"

    scenario_passed = [
        RuleScenarioParams(
            "du command completes successfully",
            {validation_cmd: CmdOutput(out="", return_code=0)},
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "du command times out",
            {validation_cmd: CmdOutput(out="", return_code=124)},  # timeout returns 124
            failed_msg="'du' command hangs",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestClockSynchronized(RuleTestBase):
    """Test ClockSynchronized validator."""

    tested_type = ClockSynchronized

    validation_cmd = "timedatectl"

    timedatectl_synchronized = """               Local time: Thu 2024-02-08 18:12:45 EST
           Universal time: Thu 2024-02-08 23:12:45 UTC
                 RTC time: Thu 2024-02-08 23:12:45
                Time zone: America/New_York (EST, -0500)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no"""

    timedatectl_not_synchronized = """               Local time: Thu 2024-02-08 18:12:45 EST
           Universal time: Thu 2024-02-08 23:12:45 UTC
                 RTC time: Thu 2024-02-08 23:12:45
                Time zone: America/New_York (EST, -0500)
System clock synchronized: no
              NTP service: inactive
          RTC in local TZ: no"""

    timedatectl_ntp_inactive = """               Local time: Thu 2024-02-08 18:12:45 EST
           Universal time: Thu 2024-02-08 23:12:45 UTC
                 RTC time: Thu 2024-02-08 23:12:45
                Time zone: America/New_York (EST, -0500)
System clock synchronized: yes
              NTP service: inactive
          RTC in local TZ: no"""

    scenario_passed = [
        RuleScenarioParams(
            "clock is synchronized and NTP service is active",
            {validation_cmd: CmdOutput(out=timedatectl_synchronized, return_code=0)},
        )
    ]

    scenario_failed = [
        RuleScenarioParams(
            "clock not synchronized",
            {validation_cmd: CmdOutput(out=timedatectl_not_synchronized, return_code=0)},
            failed_msg="NTP wrong values: {'System clock synchronized': 'no', 'NTP service': 'inactive'} at 192.168.1.10",
        ),
        RuleScenarioParams(
            "NTP service inactive",
            {validation_cmd: CmdOutput(out=timedatectl_ntp_inactive, return_code=0)},
            failed_msg="NTP wrong values: {'NTP service': 'inactive'} at 192.168.1.10",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "missing required fields",
            {
                validation_cmd: CmdOutput(
                    out="""               Local time: Thu 2024-02-08 18:12:45 EST
           Universal time: Thu 2024-02-08 23:12:45 UTC""",
                    return_code=0,
                )
            },
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


class TestTooManyOpenFilesCheck(RuleTestBase):
    """Test TooManyOpenFilesCheck validator."""

    tested_type = TooManyOpenFilesCheck

    grep_cmd = "grep -n -E 'Too many open files' /var/log/messages 2>/dev/null"
    ulimit_cmd = "ulimit -n"
    find_cmd = (
        "find /proc/ 2>/dev/null | grep -E '/proc/[0-9]+/fd/' | "
        "sed 's/\\/fd\\/.*/\\/fd\\//g' | sort | uniq -c | sort -n -r -k1"
    )

    scenario_passed = [
        RuleScenarioParams(
            "no errors in logs",
            {grep_cmd: CmdOutput(out="", return_code=1)},
        ),
        RuleScenarioParams(
            "errors in logs but no processes exceeded limit",
            {
                grep_cmd: CmdOutput(out="123:some error: Too many open files", return_code=0),
                ulimit_cmd: CmdOutput(out="1024", return_code=0),
                find_cmd: CmdOutput(out="     500 /proc/1234/fd/\n     400 /proc/5678/fd/", return_code=0),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "process exceeds file descriptor limit",
            {
                grep_cmd: CmdOutput(out="123:some error: Too many open files", return_code=0),
                ulimit_cmd: CmdOutput(out="1000", return_code=0),
                find_cmd: CmdOutput(out="    1200 /proc/1234/fd/\n     400 /proc/5678/fd/", return_code=0),
                "prlimit -p 1234 --nofile -o HARD --noheadings 2>/dev/null": CmdOutput(
                    out="1100", return_code=0
                ),
                "grep Name /proc/1234/status 2>/dev/null": CmdOutput(out="Name:\tmyprocess", return_code=0),
            },
            failed_msg="following processes opened files limit was exceeded:\nproc name 'myprocess' pid 1234 has 1200 open files. limit is 1100",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)


class TestSelinuxMode(RuleTestBase):
    """Test SelinuxMode validator."""

    tested_type = SelinuxMode

    validation_cmd = "/usr/sbin/getenforce"

    scenario_passed = [
        RuleScenarioParams(
            "SELinux is enforcing",
            {validation_cmd: CmdOutput(out="Enforcing", return_code=0)},
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "SELinux is permissive",
            {validation_cmd: CmdOutput(out="Permissive", return_code=0)},
            failed_msg="SELinux in permissive mode",
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "SELinux is disabled",
            {validation_cmd: CmdOutput(out="Disabled", return_code=0)},
            failed_msg="SELinux is disabled",
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "unknown SELinux mode",
            {validation_cmd: CmdOutput(out="Unknown", return_code=0)},
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


class TestAuditdBacklogLimit(RuleTestBase):
    """Test AuditdBacklogLimit validator."""

    tested_type = AuditdBacklogLimit

    validation_cmd = "/usr/sbin/auditctl -s"

    # Note: get_output_from_run_cmd strips output, and _measure_auditd_stats_n_times
    # concatenates it 10 times. Test data should not have trailing newlines to match.
    auditctl_ok = """enabled 1
failure 1
pid 1234
rate_limit 0
backlog_limit 8192
backlog 100
lost 0
backlog_wait_time 60000
backlog_wait_time_actual 0"""

    auditctl_high_backlog = """enabled 1
failure 1
pid 1234
rate_limit 0
backlog_limit 8192
backlog 7000
lost 0
backlog_wait_time 60000
backlog_wait_time_actual 0"""

    def _init_validation_object(self, tested_object, scenario_params):
        """Override to make _measure_auditd_stats_n_times sample only once."""
        # Call parent init first
        super()._init_validation_object(tested_object, scenario_params)

        # Wrap the original method to force n=1 (single sample instead of 10)
        original_measure = tested_object._measure_auditd_stats_n_times
        tested_object._measure_auditd_stats_n_times = lambda cmd, n=1, wait_seconds=0: original_measure(cmd, n=1, wait_seconds=0)

    scenario_passed = [
        RuleScenarioParams(
            "auditd backlog within limits",
            {validation_cmd: CmdOutput(out=auditctl_ok, return_code=0)},
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "auditd backlog utilization high",
            {validation_cmd: CmdOutput(out=auditctl_high_backlog, return_code=0)},
            failed_msg="Auditd backlog risk\nAuditd backlog utilization is 85.4% >= 80.0%: backlog=7000, backlog_limit=8192",
        ),
        # Note: "auditd lost messages" scenario requires sequential different outputs
        # (to detect increasing lost count) which the current mocking framework doesn't support.
        # The rule samples auditctl 10 times and detects if lost count increases between samples.
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "missing backlog_limit",
            {
                validation_cmd: CmdOutput(
                    out="""enabled 1
failure 1
pid 1234""",
                    return_code=0,
                )
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)


class TestYumlockFileCheck(RuleTestBase):
    """Test YumlockFileCheck validator."""

    tested_type = YumlockFileCheck

    validation_cmd = "ls /var/run/yum.pid"

    scenario_passed = [
        RuleScenarioParams(
            "yum.pid does not exist",
            {validation_cmd: CmdOutput(out="", return_code=2)},  # ls returns 2 when file not found
        )
    ]

    scenario_warning = [
        RuleScenarioParams(
            "yum.pid exists",
            {validation_cmd: CmdOutput(out="/var/run/yum.pid", return_code=0)},
            failed_msg="/var/run/yum.pid file exists, yum process may be in hung status",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_warning)
    def test_scenario_warning(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_warning(self, scenario_params, tested_object)
