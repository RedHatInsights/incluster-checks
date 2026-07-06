"""
Cluster architecture overview collection.

Collects a structured, read-only snapshot of what the cluster IS — identity,
topology, network, storage, identity providers, and installed operators —
via the cluster API. Contributed from the ocp-analyzer project.
"""

from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.parsing_utils import parse_json

VERSION_HISTORY_LIMIT = 12


class ClusterArchitectureOverview(OrchestratorRule):
    """Collect a read-only architecture overview of the cluster.

    Gathers cluster identity (version, channel, platform, base domain),
    topology (nodes by role, control-plane topology), network (CNI type,
    cluster/service CIDRs, MTU), storage classes, identity providers, and
    installed operators into a structured INFO result.

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
        infrastructure = self._get_resource(["infrastructure", "cluster"]) or {}

        overview = {
            "cluster_identity": self._collect_cluster_identity(infrastructure),
            "topology": self._collect_topology(infrastructure),
            "network": self._collect_network(),
            "storage": self._collect_storage(),
            "identity_providers": self._collect_identity_providers(),
            "operators": self._collect_operators(),
        }

        return RuleResult.info(self._build_summary(overview), system_info=overview)

    def _get_resource(self, resource_args: list, required: bool = False) -> dict | None:
        """Fetch a cluster resource as parsed JSON.

        Args:
            resource_args: Arguments for `oc get` (e.g. ["network.config", "cluster"])
            required: If True, a failed command raises UnExpectedSystemOutput
                      (rule becomes SKIP); otherwise None is returned

        Returns:
            Parsed resource dict, or None if unavailable and not required
        """
        args = [*resource_args, "-o", "json"]
        return_code, output, _ = self.oc_api.run_oc_command("get", args, timeout=45, raise_on_error=required)
        if return_code != 0:
            return None
        return parse_json(output, f"oc get {' '.join(args)}", self.get_host_ip())

    def _collect_cluster_identity(self, infrastructure: dict) -> dict:
        """Collect version, channel, cluster ID, platform, and base domain."""
        cluster_version = self._get_resource(["clusterversion", "version"], required=True)
        spec = cluster_version.get("spec", {})
        status = cluster_version.get("status", {})
        identity = {
            "version": status.get("desired", {}).get("version"),
            "channel": spec.get("channel"),
            "cluster_id": spec.get("clusterID"),
            "version_history": [entry.get("version") for entry in status.get("history", [])[:VERSION_HISTORY_LIMIT]],
        }

        infra_status = infrastructure.get("status", {})
        identity["platform"] = infra_status.get("platformStatus", {}).get("type")
        identity["infrastructure_name"] = infra_status.get("infrastructureName")
        identity["api_server_url"] = infra_status.get("apiServerURL")

        dns_config = self._get_resource(["dns.config", "cluster"])
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

        nodes = self._get_resource(["nodes"])
        if not nodes:
            return topology

        items = nodes.get("items", [])
        nodes_by_role = {}
        kubelet_versions = set()
        os_images = set()
        for node in items:
            for role in self._get_node_roles(node):
                nodes_by_role[role] = nodes_by_role.get(role, 0) + 1
            node_info = node.get("status", {}).get("nodeInfo", {})
            if node_info.get("kubeletVersion"):
                kubelet_versions.add(node_info["kubeletVersion"])
            if node_info.get("osImage"):
                os_images.add(node_info["osImage"])

        topology["node_count"] = len(items)
        topology["nodes_by_role"] = nodes_by_role
        topology["kubelet_versions"] = sorted(kubelet_versions)
        topology["os_images"] = sorted(os_images)
        return topology

    @staticmethod
    def _get_node_roles(node: dict) -> list:
        """Extract role names from a node's node-role.kubernetes.io/* labels."""
        labels = node.get("metadata", {}).get("labels", {})
        roles = [label.split("/", 1)[1] for label in labels if label.startswith("node-role.kubernetes.io/")]
        return sorted(roles) if roles else ["unknown"]

    def _collect_network(self) -> dict:
        """Collect CNI type, cluster/service CIDRs, and MTU."""
        network_config = self._get_resource(["network.config", "cluster"])
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
        storage_classes = self._get_resource(["storageclass"])
        if not storage_classes:
            return {}

        classes = []
        default_classes = []
        for storage_class in storage_classes.get("items", []):
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
        oauth = self._get_resource(["oauth", "cluster"])
        if not oauth:
            return []

        providers = oauth.get("spec", {}).get("identityProviders") or []
        return [{"name": provider.get("name"), "type": provider.get("type")} for provider in providers]

    def _collect_operators(self) -> list:
        """Collect installed operator subscriptions (name, namespace, channel, CSV)."""
        subscriptions = self._get_resource(["subscriptions.operators.coreos.com", "--all-namespaces"])
        if not subscriptions:
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
        """Build a one-line human-readable summary of the overview."""
        identity = overview["cluster_identity"]
        topology = overview["topology"]
        network = overview["network"]

        nodes_by_role = topology.get("nodes_by_role") or {}
        roles_summary = ", ".join(f"{count}x {role}" for role, count in sorted(nodes_by_role.items()))
        return (
            f"OpenShift {identity.get('version') or 'unknown'} "
            f"on {identity.get('platform') or 'unknown platform'} | "
            f"{topology.get('node_count', 0)} nodes ({roles_summary or 'roles unknown'}) | "
            f"CNI: {network.get('network_type') or 'unknown'} | "
            f"operators: {len(overview['operators'])}"
        )
