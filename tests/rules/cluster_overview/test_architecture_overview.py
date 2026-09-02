"""Tests for ClusterArchitectureOverview rule."""

import json

import pytest

from in_cluster_checks.rules.cluster_overview.architecture_overview import ClusterArchitectureOverview
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase

CLUSTER_VERSION_JSON = json.dumps(
    {
        "spec": {"channel": "stable-4.16", "clusterID": "11111111-2222-3333-4444-555555555555"},
        "status": {
            "desired": {"version": "4.16.21"},
            "history": [{"version": "4.16.21"}, {"version": "4.16.20"}],
        },
    }
)

INFRASTRUCTURE_JSON = json.dumps(
    {
        "status": {
            "platformStatus": {"type": "BareMetal"},
            "infrastructureName": "prod-x7k2p",
            "apiServerURL": "https://api.prod.example.com:6443",
            "controlPlaneTopology": "HighlyAvailable",
            "infrastructureTopology": "HighlyAvailable",
        }
    }
)

DNS_CONFIG_JSON = json.dumps({"spec": {"baseDomain": "prod.example.com"}})

NODES_JSON = json.dumps(
    {
        "items": [
            {
                "metadata": {
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "node-role.kubernetes.io/master": "",
                    }
                },
                "status": {
                    "nodeInfo": {
                        "kubeletVersion": "v1.29.8",
                        "osImage": "Red Hat Enterprise Linux CoreOS 416.94",
                    }
                },
            },
            {
                "metadata": {"labels": {"node-role.kubernetes.io/worker": ""}},
                "status": {
                    "nodeInfo": {
                        "kubeletVersion": "v1.29.8",
                        "osImage": "Red Hat Enterprise Linux CoreOS 416.94",
                    }
                },
            },
        ]
    }
)

NETWORK_CONFIG_JSON = json.dumps(
    {
        "status": {
            "networkType": "OVNKubernetes",
            "clusterNetwork": [{"cidr": "10.128.0.0/14"}],
            "serviceNetwork": ["172.30.0.0/16"],
            "clusterNetworkMTU": 1400,
        }
    }
)

STORAGE_CLASSES_JSON = json.dumps(
    {
        "items": [
            {
                "metadata": {
                    "name": "ocs-storagecluster-ceph-rbd",
                    "annotations": {"storageclass.kubernetes.io/is-default-class": "true"},
                },
                "provisioner": "openshift-storage.rbd.csi.ceph.com",
            },
            {
                "metadata": {"name": "ocs-storagecluster-cephfs"},
                "provisioner": "openshift-storage.cephfs.csi.ceph.com",
            },
        ]
    }
)

OAUTH_JSON = json.dumps({"spec": {"identityProviders": [{"name": "corp-ldap", "type": "LDAP"}]}})

SUBSCRIPTIONS_JSON = json.dumps(
    {
        "items": [
            {
                "metadata": {"name": "odf-operator", "namespace": "openshift-storage"},
                "spec": {"name": "odf-operator", "channel": "stable-4.16"},
                "status": {"installedCSV": "odf-operator.v4.16.3"},
            }
        ]
    }
)

SUBSCRIPTIONS_KEY = ("get", ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"))

FULL_CLUSTER_OC_OUTPUTS = {
    ("get", ("infrastructure", "cluster", "-o", "json")): CmdOutput(INFRASTRUCTURE_JSON),
    ("get", ("clusterversion", "version", "-o", "json")): CmdOutput(CLUSTER_VERSION_JSON),
    ("get", ("dns.config", "cluster", "-o", "json")): CmdOutput(DNS_CONFIG_JSON),
    ("get", ("nodes", "-o", "json")): CmdOutput(NODES_JSON),
    ("get", ("network.config", "cluster", "-o", "json")): CmdOutput(NETWORK_CONFIG_JSON),
    ("get", ("storageclass", "-o", "json")): CmdOutput(STORAGE_CLASSES_JSON),
    ("get", ("oauth", "cluster", "-o", "json")): CmdOutput(OAUTH_JSON),
    SUBSCRIPTIONS_KEY: CmdOutput(SUBSCRIPTIONS_JSON),
}

RBAC_DENIED = CmdOutput("", return_code=1, err="Error from server (Forbidden)")

PARTIAL_CLUSTER_OC_OUTPUTS = {
    ("get", ("infrastructure", "cluster", "-o", "json")): RBAC_DENIED,
    ("get", ("clusterversion", "version", "-o", "json")): CmdOutput(CLUSTER_VERSION_JSON),
    ("get", ("dns.config", "cluster", "-o", "json")): RBAC_DENIED,
    ("get", ("nodes", "-o", "json")): RBAC_DENIED,
    ("get", ("network.config", "cluster", "-o", "json")): RBAC_DENIED,
    ("get", ("storageclass", "-o", "json")): RBAC_DENIED,
    ("get", ("oauth", "cluster", "-o", "json")): RBAC_DENIED,
    SUBSCRIPTIONS_KEY: RBAC_DENIED,
}

# Resources readable but empty/minimal: no IdPs, no storage classes, no
# subscriptions, a node without role labels — distinct from RBAC denial.
EMPTY_CLUSTER_OC_OUTPUTS = {
    ("get", ("infrastructure", "cluster", "-o", "json")): CmdOutput(INFRASTRUCTURE_JSON),
    ("get", ("clusterversion", "version", "-o", "json")): CmdOutput(CLUSTER_VERSION_JSON),
    ("get", ("dns.config", "cluster", "-o", "json")): CmdOutput(json.dumps({})),
    ("get", ("nodes", "-o", "json")): CmdOutput(json.dumps({"items": [{"metadata": {"labels": {}}, "status": {}}]})),
    ("get", ("network.config", "cluster", "-o", "json")): CmdOutput(json.dumps({"status": {}})),
    ("get", ("storageclass", "-o", "json")): CmdOutput(json.dumps({"items": []})),
    ("get", ("oauth", "cluster", "-o", "json")): CmdOutput(json.dumps({"spec": {}})),
    SUBSCRIPTIONS_KEY: CmdOutput(json.dumps({"items": []})),
}


class TestClusterArchitectureOverview(RuleTestBase):
    """Test ClusterArchitectureOverview rule."""

    tested_type = ClusterArchitectureOverview

    scenario_info = [
        RuleScenarioParams(
            "full overview collected on a healthy cluster",
            oc_cmd_output_dict=FULL_CLUSTER_OC_OUTPUTS,
            info_msg=(
                "OpenShift 4.16.21 on BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
        RuleScenarioParams(
            "partial overview when only ClusterVersion is readable",
            oc_cmd_output_dict=PARTIAL_CLUSTER_OC_OUTPUTS,
            info_msg=(
                "OpenShift 4.16.21 on unknown platform | " "0 nodes (roles unknown) | " "CNI: unknown | operators: 0"
            ),
        ),
        RuleScenarioParams(
            "overview on a minimal cluster with readable but empty resources",
            oc_cmd_output_dict=EMPTY_CLUSTER_OC_OUTPUTS,
            info_msg=("OpenShift 4.16.21 on BareMetal | " "1 nodes (1x unknown) | " "CNI: unknown | operators: 0"),
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "rule is skipped when ClusterVersion cannot be read",
            oc_cmd_output_dict={
                ("get", ("infrastructure", "cluster", "-o", "json")): RBAC_DENIED,
                ("get", ("clusterversion", "version", "-o", "json")): RBAC_DENIED,
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_info)
    def test_scenario_info(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_info(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_unexpected_system_output)
    def test_scenario_unexpected_system_output(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_unexpected_system_output(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_info[:1])
    def test_system_info_structure(self, scenario_params, tested_object):
        """Verify the structured overview data returned in system_info."""
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

        overview = result.system_info
        identity = overview["cluster_identity"]
        assert identity["version"] == "4.16.21"
        assert identity["channel"] == "stable-4.16"
        assert identity["platform"] == "BareMetal"
        assert identity["base_domain"] == "prod.example.com"
        assert identity["version_history"] == ["4.16.21", "4.16.20"]

        topology = overview["topology"]
        assert topology["control_plane_topology"] == "HighlyAvailable"
        assert topology["node_count"] == 2
        assert topology["nodes_by_role"] == {"control-plane": 1, "master": 1, "worker": 1}
        assert topology["kubelet_versions"] == ["v1.29.8"]

        network = overview["network"]
        assert network["network_type"] == "OVNKubernetes"
        assert network["cluster_network"] == ["10.128.0.0/14"]
        assert network["service_network"] == ["172.30.0.0/16"]
        assert network["cluster_network_mtu"] == 1400

        storage = overview["storage"]
        assert storage["default_storage_classes"] == ["ocs-storagecluster-ceph-rbd"]
        assert len(storage["storage_classes"]) == 2

        assert overview["identity_providers"] == [{"name": "corp-ldap", "type": "LDAP"}]

        assert overview["operators"] == [
            {
                "name": "odf-operator",
                "namespace": "openshift-storage",
                "channel": "stable-4.16",
                "installed_csv": "odf-operator.v4.16.3",
            }
        ]

    @pytest.mark.parametrize("scenario_params", scenario_info[2:])
    def test_system_info_structure_empty_cluster(self, scenario_params, tested_object):
        """Verify empty-but-readable resources yield empty sections, not failures."""
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

        overview = result.system_info
        assert overview["cluster_identity"].get("base_domain") is None
        assert overview["topology"]["nodes_by_role"] == {"unknown": 1}
        assert overview["network"]["network_type"] is None
        assert overview["storage"] == {"storage_classes": [], "default_storage_classes": []}
        assert overview["identity_providers"] == []
        assert overview["operators"] == []
