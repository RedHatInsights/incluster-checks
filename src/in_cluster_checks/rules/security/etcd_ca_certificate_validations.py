"""
etcd signer CA certificate expiry validation rule.

The etcd signer CA is valid for 10 years. If it expires, every certificate it
signed becomes invalid and the etcd cluster stops working, which takes the whole
control plane down. Rather than re-deriving the CA expiry, this rule leverages
the built-in OpenShift monitoring alerts:

- etcdSignerCAExpirationWarning:  fires at 730 days (2 years) remaining
- etcdSignerCAExpirationCritical: fires at 365 days (1 year) remaining

The rule queries the in-cluster Prometheus alerts API and reports based on which
alert (if any) is firing.
"""

import json

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives


class EtcdCaExpiryCheck(OrchestratorRule):
    """
    Check whether the etcd signer CA certificate is approaching expiry.

    Queries the in-cluster Prometheus alerts API for the built-in etcd signer CA
    expiration alerts and reports based on which one is firing:

    - etcdSignerCAExpirationCritical firing (~1 year remaining) -> FAILED
    - etcdSignerCAExpirationWarning firing (~2 years remaining) -> WARNING
    - neither firing -> PASSED

    Only alerts in the "firing" state are acted on (pending/inactive are ignored),
    and the firing decision is OpenShift's own, so the rule mirrors the cluster's
    authoritative view rather than re-deriving certificate expiry.

    Severity: CRITICAL - if the etcd signer CA expires, all etcd certificates
    become invalid and the control plane goes down.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "etcd_ca_expiry_check"
    title = "Check etcd signer CA certificate expiry"
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/460718198",
    ]

    MONITORING_NAMESPACE = "openshift-monitoring"
    PROMETHEUS_LABEL = "app.kubernetes.io/name=prometheus"
    PROMETHEUS_CONTAINER = "prometheus"
    ALERTS_URL = "http://localhost:9090/api/v1/alerts"

    WARNING_ALERT = "etcdSignerCAExpirationWarning"
    CRITICAL_ALERT = "etcdSignerCAExpirationCritical"

    def is_prerequisite_fulfilled(self):
        """Check if Prometheus pod is available in the monitoring namespace."""
        self._prometheus_pod_name = self._get_prometheus_pod_name().strip()
        if not self._prometheus_pod_name:
            return PrerequisiteResult.not_met(f"Prometheus pod not found in {self.MONITORING_NAMESPACE} namespace")
        return PrerequisiteResult.met()

    def run_rule(self):
        """Query Prometheus alerts and evaluate the etcd signer CA expiry state."""
        alerts = self._get_firing_alerts()
        return self._evaluate_alerts(alerts)

    def _evaluate_alerts(self, alerts):
        """
        Build a RuleResult from the list of firing etcd CA alerts.

        Args:
            alerts: List of firing alert dicts (alertname, severity, state, activeAt)
                    for the etcd signer CA alertnames.

        Returns:
            RuleResult: FAILED if the critical alert is firing, WARNING if only the
            warning alert is firing, PASSED otherwise.
        """
        critical = []
        warning = []
        for alert in alerts:
            alertname = alert.get("alertname", "")
            if alertname == self.CRITICAL_ALERT:
                critical.append(alert)
            elif alertname == self.WARNING_ALERT:
                warning.append(alert)

        system_info = self._build_system_info(alerts)

        if critical:
            return RuleResult.failed(
                f"CRITICAL: etcd signer CA certificate is expiring - alert "
                f"'{self.CRITICAL_ALERT}' is firing (~1 year or less remaining).\n"
                f"If the etcd signer CA expires, all etcd certificates become invalid "
                f"and the control plane goes down. Rotate the etcd signer CA before it expires.",
                system_info=system_info,
            )

        if warning:
            return RuleResult.warning(
                f"etcd signer CA certificate is approaching expiry - alert "
                f"'{self.WARNING_ALERT}' is firing (~2 years or less remaining).\n"
                f"Plan rotation of the etcd signer CA before it reaches the critical threshold.",
                system_info=system_info,
            )

        return RuleResult.passed("etcd signer CA certificate expiry alerts are not firing")

    def _build_system_info(self, alerts):
        """Build structured table data for the firing etcd CA alerts."""
        rows = [
            [alert["alertname"], alert.get("severity", "N/A"), alert.get("state", "N/A"), alert.get("activeAt", "N/A")]
            for alert in alerts
        ]
        return {
            "headers": ["Alert", "Severity", "State", "Active Since"],
            "rows": rows,
        }

    def _get_firing_alerts(self):
        """
        Query the Prometheus alerts API and return firing etcd signer CA alerts.

        Returns:
            List of dicts with keys: alertname, severity, state, activeAt.

        Raises:
            UnExpectedSystemOutput: If the alerts cannot be retrieved or parsed.
        """
        alerts_response = self._query_prometheus_alerts()
        alerts = alerts_response.get("data", {}).get("alerts", [])

        firing = []
        for alert in alerts:
            labels = alert.get("labels", {})
            alertname = labels.get("alertname", "")
            if alertname in (self.WARNING_ALERT, self.CRITICAL_ALERT) and alert.get("state") == "firing":
                firing.append(
                    {
                        "alertname": alertname,
                        "severity": labels.get("severity", ""),
                        "state": alert.get("state", ""),
                        "activeAt": alert.get("activeAt", ""),
                    }
                )
        return firing

    def _query_prometheus_alerts(self):
        """
        Query the in-cluster Prometheus alerts API.

        Returns:
            dict: Parsed JSON response from the Prometheus /api/v1/alerts endpoint.
                  Response must have status="success" and a data.alerts array.

        Raises:
            UnExpectedSystemOutput: If the query, JSON parsing, or response
                                    indicates an error.
        """
        _, out, _ = self.oc_api.run_oc_command(
            "exec",
            [
                "-n",
                self.MONITORING_NAMESPACE,
                self._prometheus_pod_name,
                "-c",
                self.PROMETHEUS_CONTAINER,
                "--",
                "curl",
                "-s",
                self.ALERTS_URL,
            ],
            timeout=45,
        )

        try:
            response = json.loads(out)
        except json.JSONDecodeError as e:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"oc exec -n {self.MONITORING_NAMESPACE} {self._prometheus_pod_name}"
                f" -c {self.PROMETHEUS_CONTAINER} -- curl -s {self.ALERTS_URL}",
                output=out,
                message=f"Failed to parse Prometheus alerts JSON: {e}",
            )

        # Reject error responses (e.g., {"status": "error", "errorType": "...", "error": "..."})
        if response.get("status") != "success":
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"oc exec -n {self.MONITORING_NAMESPACE} {self._prometheus_pod_name}"
                f" -c {self.PROMETHEUS_CONTAINER} -- curl -s {self.ALERTS_URL}",
                output=out,
                message=f"Prometheus API returned error status: {response.get('status', 'unknown')}",
            )

        return response

    def _get_prometheus_pod_name(self):
        """
        Get name of a Prometheus pod in the monitoring namespace.

        Returns:
            str: Raw output from jsonpath query (pod name if found, empty if not).

        Raises:
            UnExpectedSystemOutput: If the command itself fails (e.g., API error, timeout).
        """
        rc, out, err = self.oc_api.run_oc_command(
            "get",
            [
                "pods",
                "-n",
                self.MONITORING_NAMESPACE,
                "-l",
                self.PROMETHEUS_LABEL,
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
            timeout=45,
            raise_on_error=False,
        )
        if rc != 0:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"oc get pods -n {self.MONITORING_NAMESPACE} -l {self.PROMETHEUS_LABEL}",
                output=err or out,
                message=f"Failed to query Prometheus pods in {self.MONITORING_NAMESPACE} namespace",
            )
        return out
