"""Tests for ClusterArchitectureOverview rule."""

from unittest.mock import Mock

import pytest
from openshift_client import OpenShiftPythonException

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.rules.cluster_overview.architecture_overview import (
    ClusterArchitectureOverview,
    NodeVirtualizationCollector,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase

CLUSTER_VERSION = {
    "spec": {"channel": "stable-4.16", "clusterID": "11111111-2222-3333-4444-555555555555"},
    "status": {
        "desired": {"version": "4.16.21"},
        "history": [{"version": "4.16.21"}, {"version": "4.16.20"}],
    },
}

INFRASTRUCTURE = {
    "status": {
        "platformStatus": {"type": "BareMetal"},
        "infrastructureName": "prod-x7k2p",
        "apiServerURL": "https://api.prod.example.com:6443",
        "controlPlaneTopology": "HighlyAvailable",
        "infrastructureTopology": "HighlyAvailable",
    }
}

DNS_CONFIG = {"spec": {"baseDomain": "prod.example.com"}}

NODES = [
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

KVM_VIRTUALIZATION = {
    "master-0": {
        "virtualization": "kvm",
        "is_virtual": True,
        "dmi": {"sys_vendor": "Red Hat", "product_name": "KVM", "bios_vendor": "SeaBIOS"},
    },
    "worker-0": {
        "virtualization": "kvm",
        "is_virtual": True,
        "dmi": {"sys_vendor": "Red Hat", "product_name": "KVM", "bios_vendor": "SeaBIOS"},
    },
}

BAREMETAL_VIRTUALIZATION = {
    "master-0": {
        "virtualization": "baremetal",
        "is_virtual": False,
        "dmi": {"sys_vendor": "Dell Inc.", "product_name": "PowerEdge R640", "bios_vendor": "Dell Inc."},
    },
}

UNDETECTED_VIRTUALIZATION = {
    "worker-0": {
        "virtualization": "unknown",
        "is_virtual": None,
        "dmi": {"sys_vendor": None, "product_name": None, "bios_vendor": None},
    },
}

VMWARE_VIRTUALIZATION = {
    "worker-0": {
        "virtualization": "vmware",
        "is_virtual": True,
        "dmi": {
            "sys_vendor": "VMware, Inc.",
            "product_name": "VMware Virtual Platform",
            "bios_vendor": "Phoenix Technologies LTD",
        },
    },
}

NETWORK_CONFIG = {
    "status": {
        "networkType": "OVNKubernetes",
        "clusterNetwork": [{"cidr": "10.128.0.0/14"}],
        "serviceNetwork": ["172.30.0.0/16"],
        "clusterNetworkMTU": 1400,
    }
}

STORAGE_CLASSES = [
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

OAUTH = {"spec": {"identityProviders": [{"name": "corp-ldap", "type": "LDAP"}]}}

SUBSCRIPTIONS = {
    "items": [
        {
            "metadata": {"name": "odf-operator", "namespace": "openshift-storage"},
            "spec": {"name": "odf-operator", "channel": "stable-4.16"},
            "status": {"installedCSV": "odf-operator.v4.16.3"},
        }
    ]
}

RBAC_DENIED = OpenShiftPythonException("Error from server (Forbidden)")
SUBSCRIPTIONS_DENIED = UnExpectedSystemOutput(
    "10.0.0.1", "oc get subscriptions.operators.coreos.com --all-namespaces -o json", "Forbidden"
)


def _resource(data: dict) -> Mock:
    """Build a mock openshift_client resource object exposing as_dict()."""
    resource = Mock()
    resource.as_dict.return_value = data
    return resource


def _by_resource_type_mock(resources_by_type: dict) -> Mock:
    """Mock an oc_api selector keyed by resource type; Exception values are raised."""

    def side_effect(resource_type, **_kwargs):
        value = resources_by_type[resource_type]
        if isinstance(value, Exception):
            raise value
        return value

    return Mock(side_effect=side_effect)


def _oc_api_mocks(single_resources: dict, storage_classes, nodes, subscriptions) -> dict:
    """Build tested_object_mock_dict for the oc_api methods used by the rule.

    Args:
        single_resources: Map of {resource_type: mock resource / None / Exception}
                          served via select_single_resource
        storage_classes: List of mock resource objects served via select_resources,
                         or an Exception to raise
        nodes: List of mock node objects, or an Exception to raise
        subscriptions: Parsed subscriptions dict, or an Exception to raise
    """
    def value_mock(value):
        return Mock(side_effect=value) if isinstance(value, Exception) else Mock(return_value=value)

    return {
        "oc_api.select_single_resource": _by_resource_type_mock(single_resources),
        "oc_api.select_resources": value_mock(storage_classes),
        "oc_api.get_all_nodes": value_mock(nodes),
        "oc_api.get_operator_subscriptions": value_mock(subscriptions),
    }


FULL_CLUSTER_MOCKS = _oc_api_mocks(
    {
        "infrastructure/cluster": _resource(INFRASTRUCTURE),
        "clusterversion/version": _resource(CLUSTER_VERSION),
        "dns.config/cluster": _resource(DNS_CONFIG),
        "network.config/cluster": _resource(NETWORK_CONFIG),
        "oauth/cluster": _resource(OAUTH),
    },
    storage_classes=[_resource(storage_class) for storage_class in STORAGE_CLASSES],
    nodes=[_resource(node) for node in NODES],
    subscriptions=SUBSCRIPTIONS,
)

PARTIAL_CLUSTER_MOCKS = _oc_api_mocks(
    {
        "infrastructure/cluster": RBAC_DENIED,
        "clusterversion/version": _resource(CLUSTER_VERSION),
        "dns.config/cluster": RBAC_DENIED,
        "network.config/cluster": RBAC_DENIED,
        "oauth/cluster": RBAC_DENIED,
    },
    storage_classes=RBAC_DENIED,
    nodes=RBAC_DENIED,
    subscriptions=SUBSCRIPTIONS_DENIED,
)

# Resources readable but empty/minimal: no IdPs, no storage classes, no
# subscriptions, a node without role labels — distinct from RBAC denial.
EMPTY_CLUSTER_MOCKS = _oc_api_mocks(
    {
        "infrastructure/cluster": _resource(INFRASTRUCTURE),
        "clusterversion/version": _resource(CLUSTER_VERSION),
        "dns.config/cluster": _resource({}),
        "network.config/cluster": _resource({"status": {}}),
        "oauth/cluster": _resource({"spec": {}}),
    },
    storage_classes=[],
    nodes=[_resource({"metadata": {"labels": {}}, "status": {}})],
    subscriptions={"items": []},
)


class TestClusterArchitectureOverview(RuleTestBase):
    """Test ClusterArchitectureOverview rule."""

    tested_type = ClusterArchitectureOverview

    scenario_info = [
        RuleScenarioParams(
            "full overview collected on a healthy cluster of VMs installed as BareMetal",
            tested_object_mock_dict=FULL_CLUSTER_MOCKS,
            data_collector_dict={NodeVirtualizationCollector: KVM_VIRTUALIZATION},
            info_msg=(
                "OpenShift 4.16.21 | Platform: kvm | "
                "Infrastructure Provider: BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
        RuleScenarioParams(
            "partial overview when only ClusterVersion is readable and no node can be reached",
            tested_object_mock_dict=PARTIAL_CLUSTER_MOCKS,
            data_collector_dict={NodeVirtualizationCollector: {}},
            info_msg=(
                "OpenShift 4.16.21 | Platform: unknown | Infrastructure Provider: unknown | "
                "0 nodes (roles unknown) | CNI: unknown | operators: 0"
            ),
        ),
        RuleScenarioParams(
            "overview on a minimal physical cluster with readable but empty resources",
            tested_object_mock_dict=EMPTY_CLUSTER_MOCKS,
            data_collector_dict={NodeVirtualizationCollector: BAREMETAL_VIRTUALIZATION},
            info_msg=(
                "OpenShift 4.16.21 | Platform: baremetal | "
                "Infrastructure Provider: BareMetal | "
                "1 node (1x unknown) | "
                "CNI: unknown | operators: 0"
            ),
        ),
        RuleScenarioParams(
            "physical masters alongside virtual workers are reported as mixed",
            tested_object_mock_dict=FULL_CLUSTER_MOCKS,
            data_collector_dict={
                NodeVirtualizationCollector: {**KVM_VIRTUALIZATION, **BAREMETAL_VIRTUALIZATION},
            },
            info_msg=(
                "OpenShift 4.16.21 | Platform: mixed | "
                "Infrastructure Provider: BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
        RuleScenarioParams(
            # The summary names the cluster-wide type; the hypervisors stay in virtualization.types
            "nodes on different hypervisors are reported as mixed",
            tested_object_mock_dict=FULL_CLUSTER_MOCKS,
            data_collector_dict={
                NodeVirtualizationCollector: {**KVM_VIRTUALIZATION, **VMWARE_VIRTUALIZATION},
            },
            info_msg=(
                "OpenShift 4.16.21 | Platform: mixed | "
                "Infrastructure Provider: BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
        RuleScenarioParams(
            # A detection gap must not be read as physical hardware
            "a node that could not be detected does not turn the cluster into mixed",
            tested_object_mock_dict=FULL_CLUSTER_MOCKS,
            data_collector_dict={
                NodeVirtualizationCollector: {**KVM_VIRTUALIZATION, **UNDETECTED_VIRTUALIZATION},
            },
            info_msg=(
                "OpenShift 4.16.21 | Platform: kvm | "
                "Infrastructure Provider: BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
        RuleScenarioParams(
            "no node detected leaves the platform unknown",
            tested_object_mock_dict=FULL_CLUSTER_MOCKS,
            data_collector_dict={NodeVirtualizationCollector: UNDETECTED_VIRTUALIZATION},
            info_msg=(
                "OpenShift 4.16.21 | Platform: unknown | "
                "Infrastructure Provider: BareMetal | "
                "2 nodes (1x control-plane, 1x master, 1x worker) | "
                "CNI: OVNKubernetes | operators: 1"
            ),
        ),
    ]

    scenario_unexpected_system_output = [
        RuleScenarioParams(
            "rule is skipped when ClusterVersion cannot be read",
            tested_object_mock_dict={
                "oc_api.select_single_resource": _by_resource_type_mock(
                    {
                        "infrastructure/cluster": RBAC_DENIED,
                        "clusterversion/version": RBAC_DENIED,
                    }
                ),
            },
        ),
        RuleScenarioParams(
            "rule is skipped when ClusterVersion does not exist",
            tested_object_mock_dict={
                "oc_api.select_single_resource": _by_resource_type_mock(
                    {
                        "infrastructure/cluster": None,
                        "clusterversion/version": None,
                    }
                ),
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
        assert identity["infrastructure_provider"] == "BareMetal"
        assert identity["base_domain"] == "prod.example.com"
        assert identity["version_history"] == ["4.16.21", "4.16.20"]

        topology = overview["topology"]
        assert topology["control_plane_topology"] == "HighlyAvailable"
        assert topology["node_count"] == 2
        assert topology["nodes_by_role"] == {"control-plane": 1, "master": 1, "worker": 1}
        assert topology["kubelet_versions"] == ["v1.29.8"]

        # Nodes are KVM guests even though the cluster was installed as BareMetal
        virtualization = overview["virtualization"]
        assert virtualization["cluster"] == "kvm"
        assert virtualization["types"] == ["kvm"]
        assert virtualization["undetected_nodes"] == []
        assert virtualization["nodes"]["master-0"]["is_virtual"] is True
        assert virtualization["nodes"]["master-0"]["dmi"]["product_name"] == "KVM"

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

    @pytest.mark.parametrize("scenario_params", scenario_info[2:3])
    def test_system_info_structure_empty_cluster(self, scenario_params, tested_object):
        """Verify empty-but-readable resources yield empty sections, not failures."""
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

        overview = result.system_info
        assert overview["cluster_identity"].get("base_domain") is None
        assert overview["topology"]["nodes_by_role"] == {"unknown": 1}
        assert overview["virtualization"]["cluster"] == "baremetal"
        assert overview["network"]["network_type"] is None
        assert overview["storage"] == {"storage_classes": [], "default_storage_classes": []}
        assert overview["identity_providers"] == []
        assert overview["operators"] == []

    @pytest.mark.parametrize("scenario_params", scenario_info[1:2])
    def test_virtualization_omitted_when_no_node_reachable(self, scenario_params, tested_object):
        """Unreachable nodes leave the section empty instead of guessing the hardware."""
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

        assert result.system_info["virtualization"] == {}

    @pytest.mark.parametrize("scenario_params", scenario_info[5:6])
    def test_undetected_nodes_are_listed_not_counted_as_a_type(self, scenario_params, tested_object):
        """An undetected node is reported as a gap, not as another kind of hardware."""
        self._init_validation_object(tested_object, scenario_params)

        with self._apply_patches(scenario_params, tested_object):
            result = tested_object.run_rule()

        virtualization = result.system_info["virtualization"]
        assert virtualization["cluster"] == "kvm"
        assert virtualization["types"] == ["kvm"]
        assert virtualization["undetected_nodes"] == ["worker-0"]


DETECT_VIRT_CMD = "systemd-detect-virt"
SYS_VENDOR_CMD = "cat /sys/class/dmi/id/sys_vendor"
PRODUCT_NAME_CMD = "cat /sys/class/dmi/id/product_name"
BIOS_VENDOR_CMD = "cat /sys/class/dmi/id/bios_vendor"

DMI_UNREADABLE = {
    SYS_VENDOR_CMD: CmdOutput("", return_code=1),
    PRODUCT_NAME_CMD: CmdOutput("", return_code=1),
    BIOS_VENDOR_CMD: CmdOutput("", return_code=1),
}


class TestNodeVirtualizationCollector(DataCollectorTestBase):
    """Test NodeVirtualizationCollector."""

    tested_type = NodeVirtualizationCollector

    scenarios = [
        DataCollectorScenarioParams(
            "libvirt guest is reported as kvm",
            {
                DETECT_VIRT_CMD: CmdOutput("kvm\n"),
                SYS_VENDOR_CMD: CmdOutput("Red Hat\n"),
                PRODUCT_NAME_CMD: CmdOutput("KVM\n"),
                BIOS_VENDOR_CMD: CmdOutput("SeaBIOS\n"),
            },
            {
                "virtualization": "kvm",
                "is_virtual": True,
                "dmi": {"sys_vendor": "Red Hat", "product_name": "KVM", "bios_vendor": "SeaBIOS"},
            },
        ),
        DataCollectorScenarioParams(
            # systemd-detect-virt exits 1 on physical hardware, which is not an error
            "physical server is reported as baremetal despite the non-zero exit code",
            {
                DETECT_VIRT_CMD: CmdOutput("none\n", return_code=1),
                SYS_VENDOR_CMD: CmdOutput("Dell Inc.\n"),
                PRODUCT_NAME_CMD: CmdOutput("PowerEdge R640\n"),
                BIOS_VENDOR_CMD: CmdOutput("Dell Inc.\n"),
            },
            {
                "virtualization": "baremetal",
                "is_virtual": False,
                "dmi": {"sys_vendor": "Dell Inc.", "product_name": "PowerEdge R640", "bios_vendor": "Dell Inc."},
            },
        ),
        DataCollectorScenarioParams(
            # The "none" output does not always reach stdout, the exit code always does
            "physical server is reported as baremetal when the failed command printed nothing",
            {
                DETECT_VIRT_CMD: CmdOutput("", return_code=1),
                SYS_VENDOR_CMD: CmdOutput("Dell Inc.\n"),
                PRODUCT_NAME_CMD: CmdOutput("PowerEdge R640\n"),
                BIOS_VENDOR_CMD: CmdOutput("Dell Inc.\n"),
            },
            {
                "virtualization": "baremetal",
                "is_virtual": False,
                "dmi": {"sys_vendor": "Dell Inc.", "product_name": "PowerEdge R640", "bios_vendor": "Dell Inc."},
            },
        ),
        DataCollectorScenarioParams(
            "a command that errored out is not read as baremetal",
            {
                DETECT_VIRT_CMD: CmdOutput("", return_code=1, err="Failed to check for virtualization: Permission denied"),
                SYS_VENDOR_CMD: CmdOutput("VMware, Inc.\n"),
                PRODUCT_NAME_CMD: CmdOutput("VMware Virtual Platform\n"),
                BIOS_VENDOR_CMD: CmdOutput("Phoenix Technologies LTD\n"),
            },
            {
                "virtualization": "vmware",
                "is_virtual": True,
                "dmi": {
                    "sys_vendor": "VMware, Inc.",
                    "product_name": "VMware Virtual Platform",
                    "bios_vendor": "Phoenix Technologies LTD",
                },
            },
        ),
        DataCollectorScenarioParams(
            "DMI signatures identify the hypervisor when systemd-detect-virt is unavailable",
            {
                DETECT_VIRT_CMD: CmdOutput("", return_code=127, err="command not found"),
                SYS_VENDOR_CMD: CmdOutput("VMware, Inc.\n"),
                PRODUCT_NAME_CMD: CmdOutput("VMware Virtual Platform\n"),
                BIOS_VENDOR_CMD: CmdOutput("Phoenix Technologies LTD\n"),
            },
            {
                "virtualization": "vmware",
                "is_virtual": True,
                "dmi": {
                    "sys_vendor": "VMware, Inc.",
                    "product_name": "VMware Virtual Platform",
                    "bios_vendor": "Phoenix Technologies LTD",
                },
            },
        ),
        DataCollectorScenarioParams(
            "no evidence at all is reported as unknown rather than baremetal",
            {
                DETECT_VIRT_CMD: CmdOutput("", return_code=127, err="command not found"),
                **DMI_UNREADABLE,
            },
            {
                "virtualization": "unknown",
                "is_virtual": None,
                "dmi": {"sys_vendor": None, "product_name": None, "bios_vendor": None},
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)
