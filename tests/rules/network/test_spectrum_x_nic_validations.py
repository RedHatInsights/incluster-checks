"""
Unit tests for Spectrum-X NIC interface naming validations.

Tests for NicInterfaceNameCollector and AreNicInterfacesRenamedPerTemplate.
"""

from unittest.mock import Mock

import openshift_client as oc
import pytest

from in_cluster_checks.rules.network.spectrum_x_nic_validations import (
    AreNicInterfacesRenamedPerTemplate,
    NicInterfaceNameCollector,
)
from tests.pytest_tools.test_data_collector_base import DataCollectorScenarioParams, DataCollectorTestBase
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase

NET_LS_CMD = "ls -l /sys/class/net/*/device"
RDMA_LS_CMD = "ls -l /sys/class/infiniband/*/device"

WORKER_LABELS = {"node-role.kubernetes.io/worker": ""}
RAIL_PCI_ADDRESSES = [["0000:18:00.0"], ["0000:1a:00.0"]]


def _mock_cr(
    name: str = "spectrum-x-interface-names",
    node_selector: dict | None = None,
    net_prefix: str = "eth_r%rail_id%_p%plane_id%",
    rdma_prefix: str = "roce_r%rail_id%",
    rail_pci_addresses: list | None = None,
):
    cr = Mock()
    cr.as_dict.return_value = {
        "metadata": {"name": name},
        "spec": {
            "nodeSelector": node_selector if node_selector is not None else {},
            "pfsPerNic": 1,
            "netDevicePrefix": net_prefix,
            "rdmaDevicePrefix": rdma_prefix,
            "railPciAddresses": rail_pci_addresses or [],
        },
    }
    return cr


def _mock_node(name: str, labels: dict | None = None):
    node = Mock()
    node.as_dict.return_value = {"metadata": {"name": name, "labels": labels or {}}}
    return node


class TestNicInterfaceNameCollector(DataCollectorTestBase):
    """Tests for NicInterfaceNameCollector."""

    tested_type = NicInterfaceNameCollector

    scenarios = [
        DataCollectorScenarioParams(
            "net and RDMA interfaces found",
            cmd_input_output_dict={
                NET_LS_CMD: CmdOutput(
                    "lrwxrwxrwx. 1 root root 0 Jan  1 00:00 /sys/class/net/eth_r0_p0/device -> ../../../0000:18:00.0\n"
                    "lrwxrwxrwx. 1 root root 0 Jan  1 00:00 /sys/class/net/eth_r1_p0/device -> ../../../0000:1a:00.0"
                ),
                RDMA_LS_CMD: CmdOutput(
                    "lrwxrwxrwx. 1 root root 0 Jan  1 00:00 /sys/class/infiniband/roce_r0/device -> ../../../0000:18:00.0\n"
                    "lrwxrwxrwx. 1 root root 0 Jan  1 00:00 /sys/class/infiniband/roce_r1/device -> ../../../0000:1a:00.0"
                ),
            },
            scenario_res={
                "net": {"0000:18:00.0": "eth_r0_p0", "0000:1a:00.0": "eth_r1_p0"},
                "rdma": {"0000:18:00.0": "roce_r0", "0000:1a:00.0": "roce_r1"},
            },
        ),
        DataCollectorScenarioParams(
            "no Spectrum-X NIC present on node",
            cmd_input_output_dict={
                NET_LS_CMD: CmdOutput("", return_code=2, err="No such file or directory"),
                RDMA_LS_CMD: CmdOutput("", return_code=2, err="No such file or directory"),
            },
            scenario_res=None,
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestAreNicInterfacesRenamedPerTemplate(RuleTestBase):
    """Tests for AreNicInterfacesRenamedPerTemplate rule."""

    tested_type = AreNicInterfacesRenamedPerTemplate

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "NicInterfaceNameTemplate CRD not found",
            tested_object_mock_dict={
                "oc_api": Mock(select_resources=Mock(side_effect=oc.OpenShiftPythonException("no matches for kind")))
            },
        ),
        RuleScenarioParams(
            "no NicInterfaceNameTemplate resources found",
            tested_object_mock_dict={"oc_api": Mock(select_resources=Mock(return_value=[]))},
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NicInterfaceNameTemplate CR exists",
            tested_object_mock_dict={
                "oc_api": Mock(select_resources=Mock(return_value=[_mock_cr(rail_pci_addresses=RAIL_PCI_ADDRESSES)]))
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    # PASSED scenario
    scenario_passed = [
        RuleScenarioParams(
            "all rails renamed correctly on all nodes",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[_mock_cr(node_selector=WORKER_LABELS, rail_pci_addresses=RAIL_PCI_ADDRESSES)]
                    ),
                    get_all_nodes=Mock(return_value=[_mock_node("worker-0", WORKER_LABELS)]),
                )
            },
            data_collector_dict={
                NicInterfaceNameCollector: {
                    "worker-0": {
                        "net": {"0000:18:00.0": "eth_r0_p0", "0000:1a:00.0": "eth_r1_p0"},
                        "rdma": {"0000:18:00.0": "roce_r0", "0000:1a:00.0": "roce_r1"},
                    }
                }
            },
        ),
    ]

    # FAILED scenarios
    scenario_failed = [
        RuleScenarioParams(
            "one rail missing renamed interface",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[_mock_cr(node_selector=WORKER_LABELS, rail_pci_addresses=RAIL_PCI_ADDRESSES)]
                    ),
                    get_all_nodes=Mock(return_value=[_mock_node("worker-0", WORKER_LABELS)]),
                )
            },
            data_collector_dict={
                NicInterfaceNameCollector: {
                    "worker-0": {
                        "net": {"0000:18:00.0": "eth_r0_p0"},
                        "rdma": {"0000:18:00.0": "roce_r0"},
                    }
                }
            },
            failed_msg=(
                "worker-0: rail 1 plane 0 (PCI 0000:1a:00.0) expected net interface 'eth_r1_p0', found 'missing'\n"
                "worker-0: rail 1 plane 0 (PCI 0000:1a:00.0) expected RDMA device 'roce_r1', found 'missing'"
            ),
        ),
        RuleScenarioParams(
            "interface present but not renamed",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[_mock_cr(node_selector=WORKER_LABELS, rail_pci_addresses=[["0000:18:00.0"]])]
                    ),
                    get_all_nodes=Mock(return_value=[_mock_node("worker-0", WORKER_LABELS)]),
                )
            },
            data_collector_dict={
                NicInterfaceNameCollector: {
                    "worker-0": {
                        "net": {"0000:18:00.0": "ens1f0"},
                        "rdma": {"0000:18:00.0": "mlx5_0"},
                    }
                }
            },
            failed_msg=(
                "worker-0: rail 0 plane 0 (PCI 0000:18:00.0) expected net interface 'eth_r0_p0', found 'ens1f0'\n"
                "worker-0: rail 0 plane 0 (PCI 0000:18:00.0) expected RDMA device 'roce_r0', found 'mlx5_0'"
            ),
        ),
        RuleScenarioParams(
            "no Spectrum-X interfaces found on node",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[_mock_cr(node_selector=WORKER_LABELS, rail_pci_addresses=[["0000:18:00.0"]])]
                    ),
                    get_all_nodes=Mock(return_value=[_mock_node("worker-0", WORKER_LABELS)]),
                )
            },
            data_collector_dict={NicInterfaceNameCollector: {"worker-0": None}},
            failed_msg="worker-0: no Spectrum-X network interfaces found on node",
        ),
        RuleScenarioParams(
            "no CR matches node labels",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _mock_cr(
                                node_selector={"node-role.kubernetes.io/other": ""},
                                rail_pci_addresses=[["0000:18:00.0"]],
                            )
                        ]
                    ),
                    get_all_nodes=Mock(return_value=[_mock_node("worker-0", WORKER_LABELS)]),
                )
            },
            data_collector_dict={
                NicInterfaceNameCollector: {
                    "worker-0": {"net": {"0000:18:00.0": "eth_r0_p0"}, "rdma": {"0000:18:00.0": "roce_r0"}}
                }
            },
            failed_msg="worker-0: no NicInterfaceNameTemplate CR matches this node's labels",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
