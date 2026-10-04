"""
Cluster architecture overview collection.

Collects a structured, read-only snapshot of what the cluster IS — identity,
topology, network, storage, identity providers, and installed operators —
via the cluster API. Contributed from the ocp-analyzer project.
"""

import openshift_client as oc

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import get_node_role_labels
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

VERSION_HISTORY_LIMIT = 12

BAREMETAL = "baremetal"
UNKNOWN_VIRTUALIZATION = "unknown"
MIXED_VIRTUALIZATION = "mixed"

# DMI strings published by common hypervisors, matched against sys_vendor,
# product_name and bios_vendor when systemd-detect-virt is unavailable
VM_DMI_SIGNATURES = {
    "kvm": ("kvm", "qemu", "rhev hypervisor", "bochs"),
    "vmware": ("vmware",),
    "microsoft": ("hyper-v", "microsoft corporation virtual machine"),
    "xen": ("xen",),
    "oracle": ("virtualbox", "innotek"),
    "parallels": ("parallels",),
    "amazon": ("amazon ec2",),
    "nutanix": ("nutanix", "ahv"),
}


class NodeVirtualizationCollector(DataCollector):
    """Detect whether a node runs on physical hardware or inside a virtual machine.

    The Infrastructure CR reports the platform OpenShift was *installed* for, which
    is BareMetal for any cluster installed without a cloud provider integration —
    including clusters whose nodes are libvirt/VMware guests. Only the node's own
    CPUID/DMI data tells what the node actually runs on.
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "collect_node_virtualization"
    title = "Collect Node Virtualization Data"
    # Nodes that cannot be reached leave a gap in the overview instead of skipping it
    raise_collection_errors = False

    def collect_data(self, **kwargs) -> dict:
        """Collect the node's virtualization type together with the DMI evidence for it."""
        dmi = {
            "sys_vendor": self._read_dmi_field(SafeCmdString("cat /sys/class/dmi/id/sys_vendor")),
            "product_name": self._read_dmi_field(SafeCmdString("cat /sys/class/dmi/id/product_name")),
            "bios_vendor": self._read_dmi_field(SafeCmdString("cat /sys/class/dmi/id/bios_vendor")),
        }
        virtualization = self._detect_virtualization(dmi)
        return {
            "virtualization": virtualization,
            "is_virtual": None if virtualization == UNKNOWN_VIRTUALIZATION else virtualization != BAREMETAL,
            "dmi": dmi,
        }

    def _read_dmi_field(self, cmd: SafeCmdString) -> str | None:
        """Read a single DMI attribute, returning None when it is absent or empty."""
        return_code, out, _ = self.run_cmd(cmd)
        return out.strip() or None if return_code == 0 else None

    def _detect_virtualization(self, dmi: dict) -> str:
        """Return the hypervisor name, "baremetal", or "unknown".

        `systemd-detect-virt` reads CPUID/DMI and exits 0 naming the hypervisor inside
        a VM. On physical hardware it exits 1, which is a detection result and not an
        error, so a non-zero exit code alone does not mean the command failed. It
        prints "none" when it does, but that output does not always reach stdout
        through `oc debug`, so exit 1 with nothing on stderr is trusted on its own.

        A real failure (the binary is missing, the command could not run) writes a
        message to stderr and falls back to raw DMI.
        """
        return_code, out, err = self.run_cmd(SafeCmdString("systemd-detect-virt"))
        detected = out.strip()

        if return_code == 0 and detected and detected != "none":
            return detected
        if return_code == 1 and not err.strip():
            return BAREMETAL
        return self._detect_virtualization_from_dmi(dmi)

    @staticmethod
    def _detect_virtualization_from_dmi(dmi: dict) -> str:
        """Match DMI vendor/product strings against known hypervisor signatures."""
        dmi_text = " ".join(value.lower() for value in dmi.values() if value)
        if not dmi_text:
            return UNKNOWN_VIRTUALIZATION

        for hypervisor, signatures in VM_DMI_SIGNATURES.items():
            if any(signature in dmi_text for signature in signatures):
                return hypervisor

        # Absence of a known signature is not proof of physical hardware
        return UNKNOWN_VIRTUALIZATION


class ClusterArchitectureOverview(OrchestratorRule):
    """Collect a read-only architecture overview of the cluster.

    Gathers cluster identity (version, channel, platform, base domain),
    topology (nodes by role, control-plane topology), virtualization (whether
    nodes are physical or VMs), network (CNI type, cluster/service CIDRs, MTU),
    storage classes, identity providers, and installed operators into a
    structured INFO result.

    The ClusterVersion resource is required; every other section degrades
    gracefully (e.g. RBAC denied, resource absent) so a partial overview
    is still reported instead of failing the whole rule.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "cluster_architecture_overview"
    title = "Cluster architecture overview"
    supported_profiles = {"general"}
    links = [
        "https://docs.openshift.com/container-platform/latest/architecture/architecture.html",
    ]

    def run_rule(self) -> RuleResult:
        """Collect all overview sections and return them as a structured INFO result."""
        infrastructure = self._get_resource("infrastructure/cluster") or {}

        overview = {
            "cluster_identity": self._collect_cluster_identity(infrastructure),
            "topology": self._collect_topology(infrastructure),
            "virtualization": self._collect_virtualization(),
            "network": self._collect_network(),
            "storage": self._collect_storage(),
            "identity_providers": self._collect_identity_providers(),
            "operators": self._collect_operators(),
        }

        return RuleResult.info(self._build_summary(overview), system_info=overview)

    def _get_resource(self, resource_type: str) -> dict | None:
        """Fetch an optional single resource via oc_api as a plain dict.

        Args:
            resource_type: Resource to select (e.g. "network.config/cluster")

        Returns:
            Resource dict, or None if the resource is absent or the query failed
            (e.g. RBAC denied), so the section degrades gracefully
        """
        try:
            resource = self.oc_api.select_single_resource(resource_type, timeout=45)
        except oc.OpenShiftPythonException:
            return None
        return resource.as_dict() if resource else None

    def _get_required_resource(self, resource_type: str) -> dict:
        """Fetch a required single resource via oc_api as a plain dict.

        Args:
            resource_type: Resource to select (e.g. "clusterversion/version")

        Returns:
            Resource dict

        Raises:
            UnExpectedSystemOutput: If the resource is absent or the query failed
                                    (rule becomes SKIP)
        """
        try:
            resource = self.oc_api.select_single_resource(resource_type, timeout=45)
        except oc.OpenShiftPythonException as error:
            raise UnExpectedSystemOutput(
                self.get_host_ip(),
                f"oc get {resource_type}",
                str(error),
                f"Failed to read required resource '{resource_type}'",
            ) from error
        if not resource:
            raise UnExpectedSystemOutput(
                self.get_host_ip(),
                f"oc get {resource_type}",
                "",
                f"Required resource '{resource_type}' not found",
            )
        return resource.as_dict()

    def _get_resource_list(self, resource_type: str) -> list[dict] | None:
        """Fetch a list of resources via oc_api as plain dicts.

        Args:
            resource_type: Resource to select (e.g. "storageclass")

        Returns:
            List of resource dicts (empty if none exist), or None if the query failed
        """
        try:
            resources = self.oc_api.select_resources(resource_type, timeout=45)
        except oc.OpenShiftPythonException:
            return None
        return [resource.as_dict() for resource in resources]

    def _collect_cluster_identity(self, infrastructure: dict) -> dict:
        """Collect version, channel, cluster ID, infrastructure provider, and base domain."""
        cluster_version = self._get_required_resource("clusterversion/version")
        spec = cluster_version.get("spec", {})
        status = cluster_version.get("status", {})
        identity = {
            "version": status.get("desired", {}).get("version"),
            "channel": spec.get("channel"),
            "cluster_id": spec.get("clusterID"),
            "version_history": [entry.get("version") for entry in status.get("history", [])[:VERSION_HISTORY_LIMIT]],
        }

        infra_status = infrastructure.get("status", {})
        identity["infrastructure_provider"] = infra_status.get("platformStatus", {}).get("type")
        identity["infrastructure_name"] = infra_status.get("infrastructureName")
        identity["api_server_url"] = infra_status.get("apiServerURL")

        dns_config = self._get_resource("dns.config/cluster")
        if dns_config:
            identity["base_domain"] = dns_config.get("spec", {}).get("baseDomain")

        return identity

    def _collect_topology(self, infrastructure: dict) -> dict:
        """Collect node counts by role, control-plane topology, and node software versions."""
        infra_status = infrastructure.get("status", {})
        topology = {
            "control_plane_topology": infra_status.get("controlPlaneTopology"),
            "infrastructure_topology": infra_status.get("infrastructureTopology"),
        }

        try:
            node_objects = self.oc_api.get_all_nodes(timeout=45)
        except oc.OpenShiftPythonException:
            return topology

        nodes_by_role = {}
        kubelet_versions = set()
        os_images = set()
        for node_object in node_objects:
            node = node_object.as_dict()
            for role in get_node_role_labels(node) or ["unknown"]:
                nodes_by_role[role] = nodes_by_role.get(role, 0) + 1
            node_info = node.get("status", {}).get("nodeInfo", {})
            if node_info.get("kubeletVersion"):
                kubelet_versions.add(node_info["kubeletVersion"])
            if node_info.get("osImage"):
                os_images.add(node_info["osImage"])

        topology["node_count"] = len(node_objects)
        topology["nodes_by_role"] = nodes_by_role
        topology["kubelet_versions"] = sorted(kubelet_versions)
        topology["os_images"] = sorted(os_images)
        return topology

    def _collect_virtualization(self) -> dict:
        """Collect per-node virtualization type and reduce it to a cluster-wide value.

        Complements `cluster_identity.infrastructure_provider`, which only reports
        the platform integration chosen at install time: a cluster installed as
        BareMetal onto libvirt guests reports provider BareMetal and
        virtualization kvm.

        Nodes whose type could not be determined are excluded from the cluster-wide
        value and listed under undetected_nodes, so a detection gap is never
        reported as a cluster running mixed hardware.

        Returns:
            Dict with the cluster-wide type, the detected types, the nodes that
            stayed undetected and the per-node detail, or an empty dict when no
            node could be reached
        """
        node_data = self.run_data_collector(NodeVirtualizationCollector)
        nodes = {node_name: data for node_name, data in node_data.items() if data}
        if not nodes:
            return {}

        undetected_nodes = sorted(
            node_name for node_name, data in nodes.items() if data["virtualization"] == UNKNOWN_VIRTUALIZATION
        )
        detected_types = {data["virtualization"] for data in nodes.values()} - {UNKNOWN_VIRTUALIZATION}

        if not detected_types:
            cluster_type = UNKNOWN_VIRTUALIZATION
        elif len(detected_types) == 1:
            cluster_type = next(iter(detected_types))
        else:
            cluster_type = MIXED_VIRTUALIZATION

        return {
            "cluster": cluster_type,
            "types": sorted(detected_types),
            "undetected_nodes": undetected_nodes,
            "nodes": nodes,
        }

    def _collect_network(self) -> dict:
        """Collect CNI type, cluster/service CIDRs, and MTU."""
        network_config = self._get_resource("network.config/cluster")
        if not network_config:
            return {}

        status = network_config.get("status", {})
        return {
            "network_type": status.get("networkType"),
            "cluster_network": [entry.get("cidr") for entry in status.get("clusterNetwork", [])],
            "service_network": status.get("serviceNetwork", []),
            "cluster_network_mtu": status.get("clusterNetworkMTU"),
        }

    def _collect_storage(self) -> dict:
        """Collect storage classes and which of them are default."""
        storage_classes = self._get_resource_list("storageclass")
        # None means the query failed (e.g. RBAC denied); an empty list is a
        # readable cluster with no storage classes and still yields a section
        if storage_classes is None:
            return {}

        classes = []
        default_classes = []
        for storage_class in storage_classes:
            metadata = storage_class.get("metadata", {})
            name = metadata.get("name")
            annotations = metadata.get("annotations") or {}
            is_default = annotations.get("storageclass.kubernetes.io/is-default-class") == "true"
            classes.append(
                {
                    "name": name,
                    "provisioner": storage_class.get("provisioner"),
                    "default": is_default,
                }
            )
            if is_default:
                default_classes.append(name)

        return {"storage_classes": classes, "default_storage_classes": default_classes}

    def _collect_identity_providers(self) -> list:
        """Collect configured identity provider names and types (no credentials)."""
        oauth = self._get_resource("oauth/cluster")
        if not oauth:
            return []

        providers = oauth.get("spec", {}).get("identityProviders") or []
        return [{"name": provider.get("name"), "type": provider.get("type")} for provider in providers]

    def _collect_operators(self) -> list:
        """Collect installed operator subscriptions (name, namespace, channel, CSV)."""
        try:
            subscriptions = self.oc_api.get_operator_subscriptions()
        except UnExpectedSystemOutput:
            return []

        operators = []
        for item in subscriptions.get("items", []):
            spec = item.get("spec", {})
            metadata = item.get("metadata", {})
            operators.append(
                {
                    "name": spec.get("name") or metadata.get("name"),
                    "namespace": metadata.get("namespace"),
                    "channel": spec.get("channel"),
                    "installed_csv": item.get("status", {}).get("installedCSV"),
                }
            )

        return sorted(operators, key=lambda operator: (operator["namespace"] or "", operator["name"] or ""))

    @staticmethod
    def _build_summary(overview: dict) -> str:
        """Build a one-line human-readable summary of the overview.

        Every segment is a value the overview already carries, so the summary and
        the consumers of the structured snapshot always say the same thing.

        The cluster platform (what the nodes run on) and the infrastructure
        provider (what OpenShift was installed for) are separate segments because
        they routinely differ — VMs installed without a cloud provider
        integration report a BareMetal provider. A platform that could not be
        detected reads as unknown, so the summary never claims hardware it could
        not verify.
        """
        identity = overview["cluster_identity"]
        topology = overview["topology"]
        network = overview["network"]
        virtualization = overview["virtualization"]

        nodes_by_role = topology.get("nodes_by_role") or {}
        roles_summary = ", ".join(f"{count}x {role}" for role, count in sorted(nodes_by_role.items()))
        node_count = topology.get("node_count", 0)
        node_word = "node" if node_count == 1 else "nodes"

        segments = [
            f"OpenShift {identity.get('version') or 'unknown'}",
            f"Platform: {virtualization.get('cluster') or UNKNOWN_VIRTUALIZATION}",
            f"Infrastructure Provider: {identity.get('infrastructure_provider') or 'unknown'}",
            f"{node_count} {node_word} ({roles_summary or 'roles unknown'})",
            f"CNI: {network.get('network_type') or 'unknown'}",
            f"operators: {len(overview['operators'])}",
        ]
        return " | ".join(segments)
