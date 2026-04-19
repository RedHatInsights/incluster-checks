"""
Etcd validation rules for OpenShift clusters.

Ported from support/HealthChecks/flows/Etcd/etcd_validations.py
These rules check etcd health, performance, and configuration on OpenShift.
"""

import json

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class EtcdRule(OrchestratorRule):
    """
    Base class for etcd validation rules.

    Provides common functionality for running etcd commands via oc rsh.
    All etcd rules run as orchestrator rules and use oc/openshift_client library.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]

    def _get_etcd_pod_name(self):
        """
        Get name of a running etcd pod using inherited _get_pod_name method.

        Returns:
            str: Pod name

        Raises:
            UnExpectedSystemOutput: If no running etcd pod found
        """
        pod_name = self.oc_api.get_pod_name("openshift-etcd", {"app": "etcd"})

        if not pod_name:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="oc get pods -n openshift-etcd -l app=etcd",
                output="",
                message="No etcd pods found in openshift-etcd namespace",
            )

        return pod_name

    def _run_etcdctl_cmd(self, etcd_cmd: SafeCmdString, pod_name=None):
        """
        Run etcdctl command inside etcd pod.

        Args:
            etcd_cmd: The etcdctl command to run (e.g., "version", "alarm list")
            pod_name: Etcd pod name (if None, will get it automatically)

        Returns:
            Tuple of (rc, stdout, stderr)
        """
        if pod_name is None:
            pod_name = self._get_etcd_pod_name()

        rc, out, err = self.oc_api.run_rsh_cmd("openshift-etcd", pod_name, etcd_cmd)
        return rc, out, err

    def _run_curl_in_pod(self, url, pod_name=None, grep_pattern=None):
        """
        Run curl command inside etcd pod with proper certificate authentication.

        Args:
            url: URL to curl
            pod_name: Etcd pod name (if None, will get it automatically)
            grep_pattern: Optional grep pattern to filter curl output

        Returns:
            Tuple of (rc, stdout, stderr)
        """
        if pod_name is None:
            pod_name = self._get_etcd_pod_name()

        # Environment variables are trusted (set by Kubernetes), only escape the URL
        if grep_pattern:
            curl_cmd = SafeCmdString(
                "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT "
                "--cacert $ETCDCTL_CACERT -XGET {url} | grep {pattern}"
            ).format(url=url, pattern=grep_pattern)
        else:
            curl_cmd = SafeCmdString(
                "curl --max-time 10 -s --key $ETCDCTL_KEY --cert $ETCDCTL_CERT --cacert $ETCDCTL_CACERT -XGET {url}"
            ).format(url=url)

        rc, out, err = self.oc_api.run_rsh_cmd("openshift-etcd", pod_name, curl_cmd)
        return rc, out, err


class EtcdBasicCheck(EtcdRule):
    """
    Check if etcd exists and is reachable.

    Ported from HealthChecks EtcdBasicValidator.
    Tests basic connectivity using etcdctl version command.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_reachable"
    title = "Check etcd exists and is reachable"

    def run_rule(self):
        """
        Test etcd connectivity using version command.

        Returns:
            RuleResult: Passed if etcd is reachable, failed otherwise
        """
        # Test etcd connectivity with version command
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl version"))

        if rc != 0:
            return RuleResult.failed(
                f"Could not connect to etcd. Command failed with rc={rc}\nError: {err}",
            )

        return RuleResult.passed(system_info={"etcd_version": out.strip()})


class EtcdAlarmCheck(EtcdRule):
    """
    Check if there are any alarms on etcd.

    Ported from HealthChecks EtcdAlarmValidator.
    Checks for etcd alarm conditions that indicate problems.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_alarm_validator"
    title = "Check if there are any alarms on etcd"

    def run_rule(self):
        """
        Check for etcd alarms.

        Returns:
            RuleResult: Passed if no alarms, failed if alarms present
        """
        # Check for alarms
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl alarm list"))

        # Empty output means no alarms
        if out.strip():
            return RuleResult.failed(
                f"Etcd has active alarms:\n{out.strip()}",
            )

        return RuleResult.passed()


class EtcdMemberCountCheck(EtcdRule):
    """
    Check if there are at least 3 etcd members.

    Ported from HealthChecks EtcdMemberNumberValidator.
    Verifies etcd has sufficient members for quorum.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_has_three_members"
    title = "Check if there are at least 3 etcd members"

    def run_rule(self):
        """
        Check etcd member count.

        Returns:
            RuleResult: Passed if >= 3 members, failed otherwise
        """
        # Get member list
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl member list -w=json"))

        try:
            members_data = json.loads(out)
            members = members_data.get("members", [])
            member_count = len(members)
        except (json.JSONDecodeError, KeyError) as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="etcdctl member list -w=json",
                output=out,
                message=f"Failed to parse etcd member list: {e}",
            )

        if member_count < 3:
            member_names = [m.get("name", "unknown") for m in members]
            return RuleResult.failed(
                f"Etcd does not have at least three members (found {member_count}): {', '.join(member_names)}",
            )

        return RuleResult.passed(system_info={"member_count": member_count})


class EtcdLeaderCheck(EtcdRule):
    """
    Check if etcd has an elected leader.

    Ported from HealthChecks EtcdLeaderValidator.
    Verifies etcd cluster has a leader for write operations.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_has_leader"
    title = "Check if etcd has a leader"

    def run_rule(self):
        """
        Check if etcd has a leader.

        Returns:
            RuleResult: Passed if leader exists, failed otherwise
        """
        # Get endpoint status as JSON
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl endpoint status -w=json"))

        if rc != 0:
            return RuleResult.failed(
                f"Failed to get endpoint status (rc={rc})\nError: {err}",
            )

        try:
            status_data = json.loads(out)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="etcdctl endpoint status -w=json",
                output=out,
                message=f"Failed to parse endpoint status JSON: {e}",
            )

        # Check if any endpoint has isLeader=true
        has_leader = any(endpoint.get("Status", {}).get("leader") for endpoint in status_data)

        if not has_leader:
            return RuleResult.failed(
                "Etcd does not have a leader",
            )

        return RuleResult.passed()


class EtcdEndpointHealthCheck(EtcdRule):
    """
    Check etcd endpoint health via /health endpoint.

    Ported from HealthChecks EtcdEndpointHealthValidator.
    Verifies all etcd endpoints are healthy.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_health_check"
    title = "Check etcd health with curl :2379/health"

    def run_rule(self):
        """
        Check etcd endpoint health.

        Returns:
            RuleResult: Passed if all endpoints healthy, failed otherwise
        """
        # Get member list to find all endpoints
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl member list -w=json"))

        try:
            members_data = json.loads(out)
            members = members_data.get("members", [])
        except (json.JSONDecodeError, KeyError) as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="etcdctl member list -w=json",
                output=out,
                message=f"Failed to parse etcd member list: {e}",
            )

        # Collect all endpoints
        endpoints = []
        for member in members:
            endpoints.extend(member.get("clientURLs", []))

        if not endpoints:
            return RuleResult.failed("No etcd endpoints found")

        # Check health of each endpoint
        unhealthy_endpoints = []
        health_details = []
        pod_name = self._get_etcd_pod_name()  # Get once and reuse for all curl calls

        for endpoint in endpoints:
            rc, health_out, health_err = self._run_curl_in_pod(f"{endpoint}/health", pod_name)

            if rc != 0:
                unhealthy_endpoints.append(endpoint)
                health_details.append(f"{endpoint}: Failed to connect (rc={rc})")
                continue

            try:
                health_data = json.loads(health_out)
                is_healthy = health_data.get("health") == "true" or health_data.get("health") is True
                health_details.append(f"{endpoint}: {health_out.strip()}")

                if not is_healthy:
                    unhealthy_endpoints.append(endpoint)
            except json.JSONDecodeError:
                unhealthy_endpoints.append(endpoint)
                health_details.append(f"{endpoint}: Invalid JSON response - {health_out}")

        if unhealthy_endpoints:
            details = "\n".join(health_details)
            return RuleResult.failed(
                f"The following etcd endpoints are not healthy: {unhealthy_endpoints}\n{details}",
            )

        return RuleResult.passed(system_info={"health_details": "\n".join(health_details)})


class EtcdWriteReadCycleCheck(EtcdRule):
    """
    Test etcd read/write functionality.

    Ported from HealthChecks EtcdWriteReadValidator.
    Performs a put/get/delete cycle with random key-value pair.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_read_write_cycle"
    title = "Write data to etcd and read it back"

    def run_rule(self):
        """
        Test etcd write and read operations.

        Returns:
            RuleResult: Passed if write/read cycle succeeds, failed otherwise
        """
        # Use UUIDs as test key/value (same as HealthChecks)
        test_key = SafeCmdString("52093047-521a-4039-baee-429e1779c268")
        test_value = SafeCmdString("40c774ad-35e4-46c5-bcd3-e1ff2b95fb67")

        # Write test data
        rc, out, err = self._run_etcdctl_cmd(
            SafeCmdString("etcdctl put {test_key} {test_value}").format(test_key=test_key, test_value=test_value)
        )
        if rc != 0:
            return RuleResult.failed(
                f"Failed to write test data to etcd (rc={rc})\nError: {err}",
            )

        # Read test data
        rc, get_out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl get {test_key}").format(test_key=test_key))
        if rc != 0:
            return RuleResult.failed(
                f"Failed to read test data from etcd (rc={rc})\nError: {err}",
            )

        # Delete test data
        self._run_etcdctl_cmd(SafeCmdString("etcdctl del {test_key}").format(test_key=test_key))

        # Verify read value matches written value
        response_lines = get_out.strip().splitlines()
        if len(response_lines) < 2:
            return RuleResult.failed(
                f"Could not read value from etcd\nResponse: {get_out}",
            )

        read_value = response_lines[1].strip()
        if read_value != str(test_value):
            return RuleResult.failed(
                f"Read value '{read_value}' does not match written value '{test_value}'",
            )

        return RuleResult.passed()


class EtcdWalFsyncPerformanceCheck(EtcdRule):
    """
    Check etcd WAL fsync duration performance.

    Ported from HealthChecks EtcdWalFsyncdurationCheck.
    Monitors Write-Ahead Log fsync performance from metrics.
    Warns if more than 1% of fsync operations exceed 8ms threshold.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_wal_fsync_duration_check"
    title = "Check etcd wal_fsync_duration_seconds with curl :2379/metrics"

    def run_rule(self):
        """
        Check WAL fsync duration metrics.

        Returns:
            RuleResult: Warning if performance is slow, passed otherwise
        """
        # Get member list to find all endpoints
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl member list -w=json"))

        try:
            members_data = json.loads(out)
            members = members_data.get("members", [])
        except (json.JSONDecodeError, KeyError) as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="etcdctl member list -w=json",
                output=out,
                message=f"Failed to parse etcd member list: {e}",
            )

        # Collect all endpoints
        endpoints = []
        for member in members:
            endpoints.extend(member.get("clientURLs", []))

        if not endpoints:
            return RuleResult.failed("No etcd endpoints found")

        # Check performance metrics for each endpoint
        slow_endpoints = []
        pod_name = self._get_etcd_pod_name()  # Get once and reuse for all curl calls

        for endpoint in endpoints:
            # Get WAL fsync metrics
            rc, metrics_out, err = self._run_curl_in_pod(
                f"{endpoint}/metrics", pod_name, grep_pattern=SafeCmdString("etcd_disk_wal_fsync_duration_seconds")
            )

            if rc != 0:
                continue  # Skip endpoints that fail to return metrics

            # Verify required histogram values are present
            if not all(k in metrics_out for k in ("Inf", "0.008", "etcd_disk_wal_fsync_duration_seconds_count")):
                raise UnExpectedSystemOutput(
                    ip=endpoint,
                    cmd=f"curl {endpoint}/metrics",
                    output=metrics_out,
                    message="Histogram values are not present in output",
                )

            # Parse metrics
            infinity_value = 0
            check_value = 0
            total_value = 0

            for line in metrics_out.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    if 'le="+Inf"' in line:
                        infinity_value = float(parts[-1])
                    elif 'le="0.008"' in line:
                        check_value = float(parts[-1])
                    elif "etcd_disk_wal_fsync_duration_seconds_count" in line:
                        total_value = float(parts[-1])

            # Calculate percentage of slow operations (> 8ms)
            if total_value > 0:
                slow_percent = ((infinity_value - check_value) / total_value) * 100

                if slow_percent > 1:
                    slow_endpoints.append((endpoint, slow_percent))

        if slow_endpoints:
            details = "\n".join(
                [f"  - {ep}: {pct:.2f}% of fsync operations exceed 8ms threshold" for ep, pct in slow_endpoints]
            )
            return RuleResult.warning(
                f"Etcd WAL fsync performance is slow on {len(slow_endpoints)} endpoint(s):\n{details}",
            )

        return RuleResult.passed()


class EtcdBackendCommitPerformanceCheck(EtcdRule):
    """
    Check etcd backend commit duration performance.

    Ported from HealthChecks EtcdBackendCommitDurationCheck.
    Monitors backend commit performance from metrics.
    Warns if more than 1% of commits exceed 32ms threshold.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_backend_commit_duration_check"
    title = "Check etcd backend_commit_duration with curl :2379/metrics"

    def run_rule(self):
        """
        Check backend commit duration metrics.

        Returns:
            RuleResult: Warning if performance is slow, passed otherwise
        """
        # Get member list to find all endpoints
        rc, out, err = self._run_etcdctl_cmd(SafeCmdString("etcdctl member list -w=json"))

        try:
            members_data = json.loads(out)
            members = members_data.get("members", [])
        except (json.JSONDecodeError, KeyError) as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="etcdctl member list -w=json",
                output=out,
                message=f"Failed to parse etcd member list: {e}",
            )

        # Collect all endpoints
        endpoints = []
        for member in members:
            endpoints.extend(member.get("clientURLs", []))

        if not endpoints:
            return RuleResult.failed("No etcd endpoints found")

        # Check performance metrics for each endpoint
        slow_endpoints = []
        pod_name = self._get_etcd_pod_name()  # Get once and reuse for all curl calls

        for endpoint in endpoints:
            # Get backend commit metrics
            rc, metrics_out, err = self._run_curl_in_pod(
                f"{endpoint}/metrics", pod_name, grep_pattern=SafeCmdString("etcd_disk_backend_commit_duration_seconds")
            )

            if rc != 0:
                continue  # Skip endpoints that fail to return metrics

            # Verify required histogram values are present
            if not all(k in metrics_out for k in ("Inf", "0.032", "etcd_disk_backend_commit_duration_seconds_count")):
                raise UnExpectedSystemOutput(
                    ip=endpoint,
                    cmd=f"curl {endpoint}/metrics",
                    output=metrics_out,
                    message="Histogram values are not present in output",
                )

            # Parse metrics
            infinity_value = 0
            check_value = 0
            total_value = 0

            for line in metrics_out.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    if 'le="+Inf"' in line:
                        infinity_value = float(parts[-1])
                    elif 'le="0.032"' in line:
                        check_value = float(parts[-1])
                    elif "etcd_disk_backend_commit_duration_seconds_count" in line:
                        total_value = float(parts[-1])

            # Calculate percentage of slow operations (> 32ms)
            if total_value > 0:
                slow_percent = ((infinity_value - check_value) / total_value) * 100

                if slow_percent > 1:
                    slow_endpoints.append((endpoint, slow_percent))

        if slow_endpoints:
            details = "\n".join(
                [f"  - {ep}: {pct:.2f}% of commits exceed 32ms threshold" for ep, pct in slow_endpoints]
            )
            return RuleResult.warning(
                f"Etcd backend commit performance is slow on {len(slow_endpoints)} endpoint(s):\n{details}",
            )

        return RuleResult.passed()
