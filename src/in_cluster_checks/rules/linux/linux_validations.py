"""
Linux validations ported from support.

Direct port from: support/HealthChecks/flows/Linux/Linux_validations.py
Adapted for OpenShift in-cluster checks.
"""

import re
import time

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import get_dict_from_string, parse_int


class SystemdServicesStatus(Rule):
    """Verify systemd services are in running state."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "systmed_services_health_check"
    title = "Verify systemd services are in running state"

    HARMLESS_LIST = [
        "systemd-network-generator",  # https://issues.redhat.com/browse/OCPBUGS-69759
        "NetworkManager-wait-online",
    ]

    def _get_service_names(self, line):
        line = line.strip()
        words = line.split()

        # Replace the Non-ASCII character "\xe2\x97\x8f" with ""
        # the dot in '*NetworkManager-wait-online.service' is read as \xe2\x97\x8f
        pretty_words = [word.strip() for word in words if not (str(word.strip()) == "\u25cf")]
        one_failed_services_full = " ".join(pretty_words)
        if one_failed_services_full:
            one_failed_services = pretty_words[0]
        else:
            one_failed_services = None
        return one_failed_services, one_failed_services_full

    def _is_in_harmless_list(self, one_failed_services):
        for service in self.HARMLESS_LIST:
            if service in one_failed_services:
                return True
        return False

    def run_rule(self):
        critical_failed_services = []
        warning_failed_services = []

        return_code, out, err = self.run_cmd("systemctl list-units | grep failed", timeout=60)

        if return_code > 0:
            return RuleResult.passed()

        if out:
            lines = out.split("\n")
            for line in lines:
                one_failed_services, one_failed_services_full = self._get_service_names(line)

                if one_failed_services and not self._is_in_harmless_list(one_failed_services):
                    # For OpenShift, treat all failed services as warnings by default
                    warning_failed_services.append(one_failed_services_full)

        if len(critical_failed_services) > 0:
            message = f"The following services are in failed state (critical):\n{critical_failed_services}"
            return RuleResult.failed(message)
        elif len(warning_failed_services) > 0:
            message = f"The following services are in failed state:\n{warning_failed_services}"
            return RuleResult.warning(message)
        else:
            return RuleResult.passed()


class IsHostReachable(Rule):
    """Verify can run simple command (echo) on host."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "is_host_reachable"
    title = "Verify can run simple command (echo) on host"

    def run_rule(self):
        ok = self.run_cmd_return_is_successful("echo 'regards to host'")
        if ok:
            return RuleResult.passed()
        else:
            return RuleResult.failed(f"host {self.get_host_ip()} not reachable")


class VerifyDuNotHang(Rule):
    """Verify 'du' command does not hang."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "verify_du_not_hang"
    title = "Verify 'du' not hang"

    def run_rule(self):
        # Use add_bash_timeout to wrap the du command with timeout (matching HC's add_bash_timeout=True)
        ret, out, err = self.run_cmd("du /tmp > /dev/null 2>&1", add_bash_timeout=True)

        # Timeout command returns 124 if the command times out
        if ret == 124:
            return RuleResult.failed("'du' command hangs")

        return RuleResult.passed()


class ClockSynchronized(Rule):
    """Verify system clock is synchronized."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "clock_synchronized"
    title = "Verify system clock is synchronized"

    def run_rule(self):
        """Validate clock synchronization using timedatectl."""
        # Get timedatectl output (will raise exception if command fails)
        out = self.get_output_from_run_cmd("timedatectl", timeout=30)

        # Parse timedatectl output using the helper function
        timedatectl_dict = get_dict_from_string(out, delimiter=":")
        failed_fields_dict = {}
        expected_dict = {"System clock synchronized": "yes", "NTP service": "active"}

        for field in expected_dict.keys():
            if field not in timedatectl_dict:
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd="timedatectl",
                    output=out,
                    message=f"No field '{field}' in the command output of 'timedatectl'",
                )
            if timedatectl_dict[field] != expected_dict[field]:
                failed_fields_dict[field] = timedatectl_dict[field]

        if failed_fields_dict:
            message = f"NTP wrong values: {failed_fields_dict} at {self.get_host_ip()}"
            return RuleResult.failed(message)

        return RuleResult.passed()


class TooManyOpenFilesCheck(Rule):
    """Validate the opened file descriptors are not exceeded the limit per proc."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "too_many_open_files_per_proc"
    title = "Validate the opened file descriptors are not exceeded the limit per proc"

    def run_rule(self):
        check_error_in_log_cmd = "grep -n -E 'Too many open files' /var/log/messages 2>/dev/null"
        exit_code, out, err = self.run_cmd(check_error_in_log_cmd)

        is_a_real_error = False
        for line in out.splitlines():
            if "grep" not in line and line.strip():
                is_a_real_error = True
                break

        if is_a_real_error:
            # Going over all the processes only if there's evidence of "Too many open files"
            open_files_limit_per_process_cmd = "ulimit -n"
            exit_code, out, err = self.run_cmd(open_files_limit_per_process_cmd)
            opened_files_limit = parse_int(out.strip(), open_files_limit_per_process_cmd, self.get_host_ip())

            # Original command from healthcheck-backup
            get_exceeded_processes_cmd = (
                "find /proc/ 2>/dev/null | grep -E '/proc/[0-9]+/fd/' | "
                "sed 's/\\/fd\\/.*/\\/fd\\//g' | sort | uniq -c | sort -n -r -k1"
            )
            exit_code, out, err = self.run_cmd(get_exceeded_processes_cmd, timeout=60)

            if not out:
                raise UnExpectedSystemOutput(self.get_host_ip(), get_exceeded_processes_cmd, "", "empty output")

            result = []
            processes_fd_lines = out.splitlines()
            for line in processes_fd_lines:
                # Extract count and PID using regex (original implementation)
                matches = re.findall(r"\d+", line)
                if len(matches) < 2:
                    continue

                fd_count_str, pid = matches[0], matches[1]
                fd_count = parse_int(fd_count_str, get_exceeded_processes_cmd, self.get_host_ip())

                if fd_count > opened_files_limit:
                    # Check specific process limit using prlimit
                    check_specific_process_limit_cmd = f"prlimit -p {pid} --nofile -o HARD --noheadings 2>/dev/null"
                    ret, limit_out, _ = self.run_cmd(check_specific_process_limit_cmd)

                    if ret == 0 and limit_out.strip():
                        specific_limit = parse_int(
                            limit_out.strip(), check_specific_process_limit_cmd, self.get_host_ip()
                        )
                        if fd_count > specific_limit:
                            # Get process name from /proc/{pid}/status
                            cmd_get_name = f"grep Name /proc/{pid}/status 2>/dev/null"
                            exit_code, name_out, _ = self.run_cmd(cmd_get_name)
                            if exit_code == 0 and name_out:
                                name = name_out.split()[1]
                            else:
                                name = "NA"

                            result.append(
                                f"proc name '{name}' pid {pid} has {fd_count_str} open files. limit is {specific_limit}"
                            )
                else:
                    # Output is sorted by count, so if count is less than limit,
                    # the next counts are smaller so no need to check them
                    break

            if len(result):
                message = "following processes opened files limit was exceeded:\n" + "\n".join(result)
                return RuleResult.failed(message)
            else:
                return RuleResult.passed()

        return RuleResult.passed()


class SelinuxMode(Rule):
    """Verify SELinux enforcing mode."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "selinux_mode"
    title = "SELinux enforcing mode"

    def run_rule(self):
        cmd = "/usr/sbin/getenforce"
        stdout = self.get_output_from_run_cmd(cmd)
        mode = stdout.strip().lower()

        if mode == "enforcing":
            return RuleResult.passed()
        elif mode == "permissive":
            return RuleResult.warning("SELinux in permissive mode")
        elif mode == "disabled":
            return RuleResult.failed("SELinux is disabled")
        else:
            raise UnExpectedSystemOutput(self.get_host_name(), cmd, f"SELinux mode unknown {mode}")


class AuditdBacklogLimit(Rule):
    """Check auditd backlog limit usage."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "auditd_backlog_limit"
    title = "Check auditd backlog limit usage"

    BACKLOG = "backlog"
    BACKLOG_LIMIT = "backlog_limit"
    LOST = "lost"

    def _measure_auditd_stats_n_times(self, cmd, n=10, wait_seconds=0.25):
        stream = ""
        for i in range(n):
            stream += self.get_output_from_run_cmd(cmd, timeout=10)
            time.sleep(wait_seconds)
            # To be more consistent with sampling period across different systems
        return stream

    def _parse_auditd_data(self, cmd, stdout):
        stdout_dict = {
            AuditdBacklogLimit.BACKLOG: 0,
            AuditdBacklogLimit.BACKLOG_LIMIT: -1,
            AuditdBacklogLimit.LOST: 0,
        }
        previous_lost = None

        for x in stdout:
            values = x.split()
            if len(values) < 2:
                raise UnExpectedSystemOutput(
                    ip=self.get_host_ip(),
                    cmd=cmd,
                    output=x,
                    message=f"Unexpected auditctl output format - expected at least 2 values, got {len(values)}",
                )

            values[1] = parse_int(values[1], cmd, self.get_host_ip())

            if (AuditdBacklogLimit.BACKLOG == values[0] or AuditdBacklogLimit.BACKLOG_LIMIT == values[0]) and values[
                1
            ] > stdout_dict[values[0]]:
                stdout_dict[values[0]] = values[1]
            elif AuditdBacklogLimit.LOST == values[0]:
                if previous_lost is not None:
                    stdout_dict[values[0]] += values[1] - previous_lost
                previous_lost = values[1]

        return stdout_dict

    def run_rule(self):
        cmd1 = "/usr/sbin/auditctl -s"
        n, wait_seconds = 10, 0.25
        stream1 = self._measure_auditd_stats_n_times(cmd=cmd1, n=n, wait_seconds=wait_seconds)

        stdout = [x for x in stream1.splitlines() if x]
        cost, return_flag = 0.8, True
        stdout_dict = self._parse_auditd_data(cmd=cmd1, stdout=stdout)

        # If no info of backlog_limit in command, raise exception
        if stdout_dict[AuditdBacklogLimit.BACKLOG_LIMIT] == -1:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=cmd1,
                output=stream1,
                message=f"Command output from '{cmd1}' didn't include backlog/lost info",
            )

        failed_msg = ""

        # Check for backlog utilization and lost message count
        if stdout_dict[AuditdBacklogLimit.BACKLOG] >= cost * stdout_dict[AuditdBacklogLimit.BACKLOG_LIMIT]:
            backlog = stdout_dict[AuditdBacklogLimit.BACKLOG]
            backlog_limit = stdout_dict[AuditdBacklogLimit.BACKLOG_LIMIT]
            utilization_pct = 100.0 * backlog / backlog_limit
            failed_msg += (
                f"\nAuditd backlog utilization is {utilization_pct:.1f}% "
                f">= {100.0 * cost:.1f}%: "
                f"{AuditdBacklogLimit.BACKLOG}={backlog}, "
                f"{AuditdBacklogLimit.BACKLOG_LIMIT}={backlog_limit}"
            )
            return_flag = False

        if stdout_dict[AuditdBacklogLimit.LOST] > 0:
            failed_msg += (
                f"\nAuditd lost messages increasing a total of "
                f"{stdout_dict[AuditdBacklogLimit.LOST]} messages in the sampled period (~{n * wait_seconds:.1f} sec)"
            )
            return_flag = False

        if not return_flag:
            return RuleResult.warning(f"Auditd backlog risk{failed_msg}")

        return RuleResult.passed()


class YumlockFileCheck(Rule):
    """Verify yum lockfile is not held by another process."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "verify_yum_lockfile_is_held_by_another_process"
    title = "Verify yum lockfile is not held by another process"

    def run_rule(self):
        # Verify yum.pid file exists or not
        return_code, output, err = self.run_cmd("ls /var/run/yum.pid")

        if return_code == 2:
            return RuleResult.passed()
        else:
            return RuleResult.warning("/var/run/yum.pid file exists, yum process may be in hung status")
