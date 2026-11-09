"""
Spectrum-X NIC interface naming validations for OpenShift clusters.

Verifies that NVIDIA Spectrum-X SuperNIC (CX-8/CX-9) physical-function interfaces
on worker nodes have been renamed according to the cluster's NicInterfaceNameTemplate
custom resource (configuration.net.nvidia.com/v1alpha1).
"""

import re
from typing import Dict, List, Optional

import openshift_client as oc

from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, PrerequisiteResult, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

NET_DEVICE_PCI_PATTERN = re.compile(
    r"/sys/class/net/([^/\s]+)/device\s*->.*/([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F])\s*$"
)
RDMA_DEVICE_PCI_PATTERN = re.compile(
    r"/sys/class/infiniband/([^/\s]+)/device\s*->.*/([0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F])\s*$"
)


class NicInterfaceNameCollector(DataCollector):
    """
    Collect the PCI-address-to-interface-name mapping for NICs and RDMA devices on a node.

    Resolves /sys/class/net/*/device and /sys/class/infiniband/*/device symlinks to
    determine which network/RDMA device name is currently bound to each PCI address.
    """

    objective_hosts = [Objectives.WORKERS]

    NET_DEVICE_CMD = SafeCmdString("ls -l /sys/class/net/*/device")
    RDMA_DEVICE_CMD = SafeCmdString("ls -l /sys/class/infiniband/*/device")

    def collect_data(self, **kwargs) -> Optional[Dict[str, Dict[str, str]]]:
        """
        Collect PCI-to-device-name mappings for net and RDMA devices.

        Returns:
            Dict with "net" and "rdma" keys, each mapping PCI address -> device name,
            or None if no Spectrum-X NIC interfaces were found on this node.
        """
        net_map = self._collect_pci_map(self.NET_DEVICE_CMD, NET_DEVICE_PCI_PATTERN)
        rdma_map = self._collect_pci_map(self.RDMA_DEVICE_CMD, RDMA_DEVICE_PCI_PATTERN)

        if not net_map and not rdma_map:
            return None

        return {"net": net_map, "rdma": rdma_map}

    def _collect_pci_map(self, cmd: SafeCmdString, pattern: re.Pattern) -> Dict[str, str]:
        """Run a symlink-listing command and map PCI address -> device name."""
        return_code, out, _ = self.run_cmd(cmd)
        if return_code != 0:
            return {}

        pci_to_device = {}
        for line in out.splitlines():
            match = pattern.search(line.strip())
            if match:
                device_name, pci_address = match.groups()
                pci_to_device[pci_address] = device_name

        return pci_to_device


class AreNicInterfacesRenamedPerTemplate(OrchestratorRule):
    """
    Verify NIC interfaces are renamed according to NicInterfaceNameTemplate configuration.

    Checks, for every rail/plane PCI address declared in the NicInterfaceNameTemplate
    custom resource, that the corresponding worker node has a network interface matching
    the configured netDevicePrefix pattern and an RDMA device matching rdmaDevicePrefix.

    The rule fails if any declared rail/plane does not have a correctly renamed interface.

    Reference:
        https://github.com/sdambo-git/spc-x-host-configuration/tree/NVIDIA-1422#nic-interface-name-template
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "are_nic_interfaces_renamed_per_template"
    title = "Verify NIC interfaces are renamed according to NicInterfaceNameTemplate configuration"
    supported_profiles = {"spectrum-x"}
    links = [
        "https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/503186727",
    ]

    CR_RESOURCE_TYPE = "nicinterfacenametemplates.configuration.net.nvidia.com"
    CR_NAMESPACE = "nvidia-network-operator"

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if a NicInterfaceNameTemplate CR exists in the nvidia-network-operator namespace.

        Returns:
            PrerequisiteResult indicating if the CR is present
        """
        try:
            crs = self.oc_api.select_resources(self.CR_RESOURCE_TYPE, namespace=self.CR_NAMESPACE, timeout=30)
        except oc.OpenShiftPythonException as e:
            error_msg = str(e).lower()
            if (
                "not found" in error_msg
                or "no matches for kind" in error_msg
                or "doesn't have a resource type" in error_msg
            ):
                return PrerequisiteResult.not_met(
                    "NicInterfaceNameTemplate CRD not found (NVIDIA Network Operator may not be installed)"
                )
            raise

        if not crs:
            return PrerequisiteResult.not_met(
                f"No NicInterfaceNameTemplate resources found in namespace {self.CR_NAMESPACE}"
            )

        return PrerequisiteResult.met()

    def run_rule(self) -> RuleResult:
        """
        Verify renamed NIC/RDMA interfaces on every worker node against the matching CR.

        Returns:
            RuleResult indicating whether all declared rails/planes are correctly renamed
        """
        crs = self.oc_api.select_resources(self.CR_RESOURCE_TYPE, namespace=self.CR_NAMESPACE, timeout=30)
        collected = self.run_data_collector(NicInterfaceNameCollector)

        exceptions = self.get_data_collector_exceptions(NicInterfaceNameCollector)
        if exceptions:
            failed_nodes = ", ".join(sorted(exceptions.keys()))
            return RuleResult.failed(
                f"Failed to collect NIC interface data from {len(exceptions)} node(s): {failed_nodes}"
            )

        node_labels = self._get_node_labels()

        failures: List[str] = []
        for node_name, node_data in collected.items():
            cr = self._find_matching_cr(crs, node_labels.get(node_name, {}))
            if cr is None:
                failures.append(f"{node_name}: no NicInterfaceNameTemplate CR matches this node's labels")
                continue
            failures.extend(self._check_node_against_cr(node_name, node_data, cr))

        if failures:
            return RuleResult.failed("\n".join(failures))

        return RuleResult.passed(f"All NIC interfaces correctly renamed on {len(collected)} node(s)")

    def _get_node_labels(self) -> Dict[str, Dict[str, str]]:
        """Build a map of node name -> labels for NicInterfaceNameTemplate nodeSelector matching."""
        nodes = self.oc_api.get_all_nodes()
        return {node.as_dict()["metadata"]["name"]: node.as_dict()["metadata"].get("labels", {}) for node in nodes}

    def _find_matching_cr(self, crs: list, node_labels: Dict[str, str]):
        """Find the first CR whose spec.nodeSelector matches the given node labels."""
        for cr in crs:
            node_selector = cr.as_dict().get("spec", {}).get("nodeSelector", {})
            if all(node_labels.get(key) == value for key, value in node_selector.items()):
                return cr
        return None

    def _check_node_against_cr(self, node_name: str, node_data: Optional[dict], cr) -> List[str]:
        """Compare a node's collected interfaces against a CR's declared rails/planes."""
        if node_data is None:
            return [f"{node_name}: no Spectrum-X network interfaces found on node"]

        spec = cr.as_dict().get("spec", {})
        net_prefix = spec.get("netDevicePrefix", "")
        rdma_prefix = spec.get("rdmaDevicePrefix", "")
        rail_pci_addresses = spec.get("railPciAddresses", [])

        net_map = node_data.get("net", {})
        rdma_map = node_data.get("rdma", {})

        failures = []
        for rail_id, plane_pci_addresses in enumerate(rail_pci_addresses):
            for plane_id, pci_address in enumerate(plane_pci_addresses):
                expected_net = self._render_template(net_prefix, rail_id, plane_id)
                expected_rdma = self._render_template(rdma_prefix, rail_id, plane_id)

                actual_net = net_map.get(pci_address)
                if actual_net != expected_net:
                    failures.append(
                        f"{node_name}: rail {rail_id} plane {plane_id} (PCI {pci_address}) expected "
                        f"net interface '{expected_net}', found '{actual_net or 'missing'}'"
                    )

                actual_rdma = rdma_map.get(pci_address)
                if actual_rdma != expected_rdma:
                    failures.append(
                        f"{node_name}: rail {rail_id} plane {plane_id} (PCI {pci_address}) expected "
                        f"RDMA device '{expected_rdma}', found '{actual_rdma or 'missing'}'"
                    )

        return failures

    @staticmethod
    def _render_template(template: str, rail_id: int, plane_id: int) -> str:
        """Substitute %rail_id% and %plane_id% tokens in a device name template."""
        return template.replace("%rail_id%", str(rail_id)).replace("%plane_id%", str(plane_id))
