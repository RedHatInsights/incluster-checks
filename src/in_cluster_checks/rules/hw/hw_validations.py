"""
Hardware validations ported from support.

Direct port from: support/HealthChecks/flows/HW/HW_validations.py
Only validators with Deployment_type.OPENSHIFT support are included.
"""

import re
from datetime import timedelta

import dateutil.parser

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.core.rule_result import PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_int


class CheckDiskUsage(Rule):
    """Verify disk space usage on nodes."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "is_disk_space_sufficient"
    title = "Verify disk space usage on computes and storage nodes"
    THRESHOLD_WARN = 80
    THRESHOLD_ERR = 90

    def run_rule(self):
        # Exclude pseudo-filesystems that don't represent real disk usage
        # This is more maintainable than inclusion-based filtering and future-proof for new filesystem types
        return_code, out, err = self.run_cmd(
            "df -hT -x tmpfs -x devtmpfs -x overlay -x composefs -x efivarfs -x squashfs -x iso9660"
        )
        disk_space_usage = re.findall(r"(\S+).*\s+([0-9]+)%\s+(.*)", out)

        failed_disks = []
        warning_disks = []

        for disk in disk_space_usage:
            usage = parse_int(disk[1], "df -h", self.get_host_ip())
            if usage > CheckDiskUsage.THRESHOLD_ERR:
                failed_disks.append(
                    f"{disk[0]} (mounted on: {disk[2]}) usage is {usage}% (threshold: {CheckDiskUsage.THRESHOLD_ERR}%)"
                )
            elif usage > CheckDiskUsage.THRESHOLD_WARN:
                warning_disks.append(
                    f"{disk[0]} (mounted on: {disk[2]}) usage is {usage}% (threshold: {CheckDiskUsage.THRESHOLD_WARN}%)"
                )

        # Failed takes precedence over warning
        if failed_disks:
            message = "Disk usage critical:\n" + "\n".join(failed_disks)
            if warning_disks:
                message += "\n\nWarnings:\n" + "\n".join(warning_disks)
            return RuleResult.failed(message)
        elif warning_disks:
            return RuleResult.warning("Disk usage warning:\n" + "\n".join(warning_disks))
        else:
            return RuleResult.passed()


class BasicFreeMemoryValidation(Rule):
    """Validate that free memory in the system is more than 15%."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "basic_memory_validation"
    title = "Validate that the free memory in the system is more than 15% on computes and storage nodes"

    THRESHOLD_RATIO = 0.15
    HIGH_PAGE_THRESHOLD_RATIO = 0.01

    def run_rule(self):
        mem_total_cmd = "cat /proc/meminfo |grep MemTotal"
        mem_avi_cmd = "cat /proc/meminfo |grep MemAvailable"

        # Get the 2nd field from output
        mem_total_out = self.get_output_from_run_cmd(mem_total_cmd)
        mem_total = float(mem_total_out.split()[1])

        mem_avi_out = self.get_output_from_run_cmd(mem_avi_cmd)
        mem_avi = float(mem_avi_out.split()[1])

        ratio = mem_avi / mem_total

        huge_pages_total_cmd = "cat /proc/meminfo |grep HugePages_Total"
        huge_pages_total_out = self.get_output_from_run_cmd(huge_pages_total_cmd)
        huge_pages_total = float(huge_pages_total_out.split()[1])

        if ratio < self.THRESHOLD_RATIO:
            # test if it is due to HugePages
            huge_pages_free_cmd = "cat /proc/meminfo |grep HugePages_Free"
            huge_pages_free_out = self.get_output_from_run_cmd(huge_pages_free_cmd)
            huge_pages_free = float(huge_pages_free_out.split()[1])

            if huge_pages_total > 0:
                huge_pages_ratio = huge_pages_free / huge_pages_total
                if huge_pages_ratio < self.HIGH_PAGE_THRESHOLD_RATIO:
                    message = (
                        f"Available memory is only {ratio * 100:.1f}% and "
                        f"Free HugePages memory is only {huge_pages_ratio * 100:.1f}%"
                    )
                    return RuleResult.failed(message)
            else:
                message = f"Available memory is only {ratio * 100:.1f}%"
                return RuleResult.failed(message)

        return RuleResult.passed()


class CPUfreqScalingGovernorValidation(Rule):
    """Validate CPU governor is configured for performance."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "cpu_configuration_speed_validation"
    title = "Validate CPU governor it configure for performance"

    def is_prerequisite_fulfilled(self):
        """Check if scaling_governor files exist (not available on VMs)."""
        return_code, _, _ = self.run_cmd("test -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
        if return_code != 0:
            return PrerequisiteResult.not_met("CPU frequency scaling governor files not available (likely a VM)")
        return PrerequisiteResult.met()

    def run_rule(self):
        lscpu_cmd = "sudo /bin/lscpu|grep '^CPU(s):'"
        lscpu = self.get_output_from_run_cmd(lscpu_cmd).strip()
        total_cpus = lscpu.split(":")[1].strip()
        total_cpus_int = parse_int(total_cpus, lscpu_cmd, self.get_host_ip())
        i = 0
        error_cpus = []
        for i in range(0, total_cpus_int):
            cmd1 = "sudo cat /sys/devices/system/cpu/cpu"
            cmd2 = "/cpufreq/scaling_governor"
            cmd = cmd1 + str(i) + cmd2
            return_code, cpu_governor_output, err = self.run_cmd(cmd)
            if return_code == 0:
                if (cpu_governor_output.strip().upper()) == "PERFORMANCE":
                    pass
                else:
                    error_cpus.append(f"CPU{i} -> {cpu_governor_output.strip()}")
            else:
                pass
        if len(error_cpus) == 0:
            return RuleResult.passed()
        else:
            message = "CPU Governor not set to PERFORMANCE\n" + "\n".join(error_cpus)
            return RuleResult.failed(message)


class TemperatureValidation(Rule):
    """Validate temperature on node using thermal zones."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "temperature_validation"
    title = "Check hardware sensor temperature using thermal zones"

    def is_prerequisite_fulfilled(self):
        """Check if thermal zone directory exists."""
        thermal_zones = self.file_utils.list_files("-d /sys/class/thermal/thermal_zone*")
        if not thermal_zones:
            return PrerequisiteResult.not_met("Thermal zones not available on this system")
        return PrerequisiteResult.met()

    def run_rule(self):
        thermal_zone_files = self.file_utils.list_files("/sys/class/thermal/thermal_zone*/temp")
        if not thermal_zone_files:
            return RuleResult.skip("No thermal zone temperature files found")

        high_temps = []

        for temp_file in thermal_zone_files:
            if not temp_file:
                continue

            # Extract zone directory from temp file path
            # e.g., "/sys/class/thermal/thermal_zone0/temp" -> "/sys/class/thermal/thermal_zone0"
            zone_dir = temp_file.rsplit("/", 1)[0]

            # Each thermal zone has a 'type' file that describes the sensor
            # e.g., "/sys/class/thermal/thermal_zone0/type" contains "x86_pkg_temp"
            type_file = f"{zone_dir}/type"

            zone_type_lines = self.file_utils.get_lines_in_file(type_file)
            if not zone_type_lines:
                zone_type = "unknown"
            else:
                zone_type = zone_type_lines[0].strip()

            temp_lines = self.file_utils.get_lines_in_file(temp_file)
            if not temp_lines:
                continue

            temp_millicelsius = temp_lines[0].strip()
            if not temp_millicelsius.isdigit():
                raise UnExpectedSystemOutput(
                    self.get_host_ip(),
                    f"cat {temp_file}",
                    temp_millicelsius,
                    f"Expected numeric temperature value for {zone_type}",
                )

            temp_celsius = int(temp_millicelsius) / 1000
            if temp_celsius >= 100:
                high_temps.append(f"{zone_type}: {temp_celsius:.1f}°C")

        if len(high_temps) == 0:
            return RuleResult.passed("All thermal sensor temperatures are ok: below 100°C")
        else:
            message = "Temperature sensor(s) exceeded threshold (100°C):\n" + "\n".join(high_temps)
            return RuleResult.failed(message)


class CpuSpeedValidation(Rule):
    """Validate that All CPU's are configured with High performance."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "cpu_speed_validation"
    title = "Validate that the All CPU's are configured with High performance"

    def _get_max_speed(self):
        cmd = "dmidecode -t processor | grep 'Max Speed' | head -n 1"
        ret, out, _ = self.run_cmd(cmd)

        if ret != 0:
            return None

        if "Max Speed:" not in out:
            return None

        speed_part = out.split("Max Speed:")[1].strip()

        if "MHz" in speed_part:
            speed_str = speed_part.replace("MHz", "").strip()
            if not speed_str.replace(".", "", 1).isdigit():
                raise UnExpectedSystemOutput(self.get_host_ip(), cmd, out, "expected numeric MHz value")
            max_speed = float(speed_str)
        elif "GHz" in speed_part:
            speed_str = speed_part.replace("GHz", "").strip()
            if not speed_str.replace(".", "", 1).isdigit():
                raise UnExpectedSystemOutput(self.get_host_ip(), cmd, out, "expected numeric GHz value")
            max_speed = float(speed_str) * 1000
        else:
            return None

        return max_speed

    def run_rule(self):
        max_cpu_speed = self._get_max_speed()

        if max_cpu_speed is None:
            return RuleResult.not_applicable("Unable to determine maximum CPU speed from dmidecode")

        cpu_speed_current_cmd = "cat /proc/cpuinfo | grep -ie mhz"
        # get the speeds
        out_speed = self.get_output_from_run_cmd(cpu_speed_current_cmd)

        # get the processor id
        cpu_processor_current_cmd = "cat /proc/cpuinfo | grep -ie processor"
        out_processor = self.get_output_from_run_cmd(cpu_processor_current_cmd)

        speed_lines = out_speed.splitlines()
        processor_lines = out_processor.splitlines()
        processor_ids = [line.split(":")[1] for line in processor_lines]

        index = 0
        bad_list = []

        for line in speed_lines:
            line_split = line.split(":")
            speed_str = line_split[1].strip()
            if not speed_str.replace(".", "", 1).isdigit():
                raise UnExpectedSystemOutput(
                    self.get_host_ip(), cpu_speed_current_cmd, line, "expected numeric MHz value in /proc/cpuinfo"
                )
            cpu_speed = float(speed_str)
            if (max_cpu_speed - cpu_speed) > 10:  # less then 10 MHZ diff can be becouse of units diffrent
                # If the cpu is more then the max cpu speed - it can be explain by turbo
                # which is allowed
                bad_list.append("CPU ID with processor id {} has speed of {} ".format(processor_ids[index], cpu_speed))
            index = index + 1

        if len(bad_list):
            message = (
                f"Some CPU are not running on maximum speed ({max_cpu_speed} MHz).\n"
                "Please note that the compute is not configured with maximum performance and therefore\n"
                "we might be facing performance impact on the VM's/containers that are hosted in this compute.\n\n"
                + "\n".join(bad_list)
            )
            return RuleResult.failed(message)
        return RuleResult.passed()


class HwSysClockCompare(Rule):
    """
    This validation compares the hwclock date/time with the system date/time. If there is a significant difference it
    fails the validation.
    The hwclock tool returns the RTC time in the same time zone as the system, so there is no need to handle time zone
    separately.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "hw_sys_clock_compare"
    CRITERIA = timedelta(seconds=3600)
    HWCLOCK_CMD = "sudo hwclock"
    SYSCLOCK_CMD = "date +'%Y-%m-%d %H:%M:%S %z'"
    title = "Compare hwclock with system clock"

    def is_prerequisite_fulfilled(self):
        """Check if hwclock command is available."""
        return_code, _, _ = self.run_cmd("which hwclock")
        if return_code != 0:
            return PrerequisiteResult.not_met("hwclock command is not available on this system")
        return PrerequisiteResult.met()

    def _get_hw_clock(self):
        """
        Formats that need to work:
        ISO 8601 format e.g.: 2024-02-08 18:12:44.404676-05:00
        older formats:
            Thu Feb  8 18:12:44 2024  -0.922926 seconds
            Thu 08 Feb 2024 07:43:25 PM UTC  -0.047875 seconds
        """
        hw_clock_output = self.get_output_from_run_cmd(self.HWCLOCK_CMD, message="hwclock cmd failed to be executed")
        try:
            hw_clock_output = hw_clock_output.splitlines()[0]
        except (IndexError, TypeError) as e:
            raise UnExpectedSystemOutput(
                self.get_host_ip(),
                cmd=self.HWCLOCK_CMD,
                output=hw_clock_output,
                message="No lines on the command output.\n{}".format(str(e)),
            )

        if "seconds" in hw_clock_output:  # non ISO 8601 format
            hw_clock_output = " ".join(hw_clock_output.split()[:-2])  # remove microseconds not recognized by parser
        return hw_clock_output

    def _get_sys_clock(self):
        sys_clock_output = self.get_output_from_run_cmd(self.SYSCLOCK_CMD, message="date cmd failed to be executed.")
        try:
            sys_clock_output = sys_clock_output.splitlines()[0]
        except (IndexError, TypeError) as e:
            raise UnExpectedSystemOutput(
                self.get_host_ip(),
                cmd=self.SYSCLOCK_CMD,
                output=sys_clock_output,
                message="No lines on the command output.\n{}".format(str(e)),
            )

        return sys_clock_output

    def _convert_str_to_datetime(self, string_datetime, cmd=""):
        try:
            datetime_obj = dateutil.parser.parse(string_datetime)
        except (ValueError, dateutil.parser.ParserError) as e:
            raise UnExpectedSystemOutput(
                self.get_host_ip(),
                cmd=cmd,
                output=string_datetime,
                message="Date/time could not be parsed.\n{}".format(str(e)),
            )
        return datetime_obj

    @staticmethod
    def _get_delta_of_datetime(date1, date2):
        if date1 > date2:
            return date1 - date2
        return date2 - date1

    @staticmethod
    def _fix_tz(hw_clock, sys_clock):
        """In some cases, the hwclock output format doesn't contain the timezone,
        in that case take the TZ from the system clock"""
        if hw_clock.tzinfo is None and sys_clock.tzinfo is not None:
            hw_clock = hw_clock.replace(tzinfo=sys_clock.tzinfo)
        return hw_clock

    def run_rule(self):
        hw_clock = self._convert_str_to_datetime(self._get_hw_clock(), self.HWCLOCK_CMD)
        sys_clock = self._convert_str_to_datetime(self._get_sys_clock(), self.SYSCLOCK_CMD)
        hw_clock = self._fix_tz(hw_clock, sys_clock)

        hw_sys_delta = self._get_delta_of_datetime(hw_clock, sys_clock)
        if hw_sys_delta > self.CRITERIA:
            message = (
                "There is a significant difference between the hw clock (RTC) and the system clock.\n"
                f"HW Clock:     {hw_clock}\nSystem Clock: {sys_clock}\n"
                f"Criteria: {self.CRITERIA.total_seconds()} seconds"
            )
            return RuleResult.failed(message)
        return RuleResult.passed()
