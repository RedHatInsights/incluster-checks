"""
OVS (Open vSwitch) base classes.

Provides common base classes for OVS/OVN validation rules and data collectors.
"""

from in_cluster_checks.core.operations import Operator, OrchestratorDataCollector
from in_cluster_checks.core.rule import Rule, RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class OvsOperatorBase(Operator):
    """
    Base class for OVS (Open vSwitch) rules and data collectors.

    Provides common OVS bridge and port discovery utilities.
    Can be inherited by both Rule subclasses and DataCollector subclasses.
    """

    def _get_nmcli_connections(self, fields: SafeCmdString, is_active=True) -> list[dict]:
        """
        Get NetworkManager connections as structured data.

        Args:
            fields: SafeCmdString with comma-separated field names
                   (e.g., SafeCmdString("TYPE,DEVICE") or SafeCmdString("NAME,DEVICE"))
            is_active: If True, only get active connections (default: True)

        Returns:
            List of dicts with field names as keys
            Example: [{'TYPE': 'bond', 'DEVICE': '<bond>'}, {'TYPE': 'ethernet', 'DEVICE': '<ethernet>'}]
            Returns empty list if no connections found or on error
        """

        fields_str = str(fields)
        fields_list = [f.strip() for f in fields_str.split(",")]

        # Build command - fields is SafeCmdString so format() won't validate it
        if is_active:
            cmd = SafeCmdString("nmcli -t -f {fields} connection show --active").format(fields=fields)
        else:
            cmd = SafeCmdString("nmcli -t -f {fields} connection show").format(fields=fields)

        output = self.get_output_from_run_cmd(cmd)

        connections = []
        for line in output.splitlines():
            if not line:
                continue

            values = line.split(":")
            if len(values) == len(fields_list):
                connection = dict(zip(fields_list, values))
                connections.append(connection)

        return connections

    def _list_proc_vlan_interfaces(self) -> set[str]:
        """
        Get all VLAN interfaces from /proc/net/vlan/.

        Uses: ls /proc/net/vlan/*

        Reads /proc/net/vlan/ directory to find all actual VLAN interfaces.
        This directory only contains files for actual VLAN interfaces.

        Returns:
            Set of VLAN interface names
        """
        # List all files in /proc/net/vlan/ (each file represents a VLAN interface)
        files = self.file_utils.list_files(SafeCmdString("/proc/net/vlan/*"))
        if not files:
            return set()

        vlan_interfaces = set()
        for file_path in files:
            # Extract interface name from path like /proc/net/vlan/bond0.204
            # Skip special files (config is not an interface)
            interface_name = file_path.split("/")[-1]
            if interface_name and interface_name != "config":
                vlan_interfaces.add(interface_name)

        return vlan_interfaces

    def _get_all_hardware_backed_interfaces(self) -> set[str]:
        """
        Get all hardware-backed interfaces in one pass.

        Fetches all interfaces from /sys/class/net/ and checks which ones
        have either a device symlink (physical NIC), bonding directory, or team directory.

        Returns:
            Set of interface names that are hardware-backed
        """
        hardware_interfaces = set()

        # Check for physical NICs (have device symlink)
        # Using ls instead of find - more reliable in containerized environments
        rc, out, _ = self.run_cmd(SafeCmdString("ls -d /sys/class/net/*/device"))
        if rc == 0:
            for line in out.strip().splitlines():
                if line.strip():
                    # Extract interface name from path like /sys/class/net/eth0/device
                    parts = line.split("/")
                    if len(parts) >= 5:
                        interface = parts[4]
                        hardware_interfaces.add(interface)

        # Check for bonding interfaces (have bonding/ directory)
        # Using ls instead of find - more reliable in containerized environments
        rc, out, _ = self.run_cmd(SafeCmdString("ls -d /sys/class/net/*/bonding"))
        if rc == 0:
            for line in out.strip().splitlines():
                if line.strip():
                    # Extract interface name from path like /sys/class/net/bond0/bonding
                    parts = line.split("/")
                    if len(parts) >= 5:
                        interface = parts[4]
                        hardware_interfaces.add(interface)

        # Check for team interfaces (have team/ directory)
        # Using ls instead of find - more reliable in containerized environments
        rc, out, _ = self.run_cmd(SafeCmdString("ls -d /sys/class/net/*/team"))
        if rc == 0:
            for line in out.strip().splitlines():
                if line.strip():
                    # Extract interface name from path like /sys/class/net/team0/team
                    parts = line.split("/")
                    if len(parts) >= 5:
                        interface = parts[4]
                        hardware_interfaces.add(interface)

        return hardware_interfaces

    def _filter_physical_ports(
        self, all_ports: list[str], hardware_interfaces: set[str], vlan_interfaces: set[str]
    ) -> list[str]:
        """
        Filter port list to include only base hardware interfaces.

        Physical ports = base hardware interfaces (bond0, eth0, ens3, SR-IOV VFs)
        Excludes VLAN sub-interfaces (bond0.204) which have IPs and shouldn't
        be validated as "physical ports" by OvsPhysicalPortHealthCheck.

        Args:
            all_ports: List of all port names from ovs-vsctl list-ports
            hardware_interfaces: Set of hardware-backed interface names (from _get_all_hardware_backed_interfaces)
            vlan_interfaces: Set of VLAN interface names (from _list_proc_vlan_interfaces)

        Returns:
            List of physical port names (VLANs excluded)
        """
        physical_ports = []
        for port in all_ports:
            # Skip VLAN interfaces explicitly (check membership in cached set)
            if port in vlan_interfaces:
                continue

            # Check if hardware-backed
            if port in hardware_interfaces:
                physical_ports.append(port)

        return physical_ports

    def _get_external_ovs_bridges(self) -> dict[str, dict[str, list[str]]]:
        """
        Get all external OVS bridges with their port information.

        External bridges have physical ports and/or VLANs (external network connectivity).
        Integration bridges (br-int) with only virtual/patch/internal ports are excluded.

        Returns:
            Dict mapping bridge names to port information
            Example: {
                'br-ex': {
                    'all_ports': ['bond0', 'bond0.204'],    # All ports (for VLAN checks)
                    'physical_ports': ['bond0']              # Base hardware only (for health checks)
                },
                'br-secondary1': {
                    'all_ports': ['bond1'],
                    'physical_ports': ['bond1']
                }
            }
            Empty dict if no external OVS bridges found or on error
        """
        # Get all bridges
        rc, br_out, _ = self.run_cmd(SafeCmdString("ovs-vsctl list-br"))
        if rc != 0:
            return {}

        all_bridges = [b.strip() for b in br_out.strip().splitlines() if b.strip()]
        if not all_bridges:
            return {}

        # Get all hardware-backed and VLAN interfaces once for all bridges (optimization)
        hardware_interfaces = self._get_all_hardware_backed_interfaces()
        vlan_interfaces = self._list_proc_vlan_interfaces()

        # Process each bridge
        result = {}
        for bridge in all_bridges:
            rc, ports_out, _ = self.run_cmd(SafeCmdString("ovs-vsctl list-ports {bridge}").format(bridge=bridge))
            if rc != 0:
                continue

            all_ports = [port.strip() for port in ports_out.strip().splitlines() if port.strip()]
            if not all_ports:
                continue

            # Filter for base hardware physical ports (pass cached sets)
            physical_ports = self._filter_physical_ports(all_ports, hardware_interfaces, vlan_interfaces)

            # Include bridge if it has base hardware OR VLANs (external network connectivity)
            # Excludes integration bridges (br-int) that only have virtual/internal/patch ports
            has_vlans = any(port in vlan_interfaces for port in all_ports)
            if physical_ports or has_vlans:
                result[bridge] = {"all_ports": all_ports, "physical_ports": physical_ports}

        return result


class OvnDetectingNodeRuleBase(OvsOperatorBase, Rule):
    """
    Base class for OVN-Kubernetes node-level rules.

    Provides common prerequisite checking for rules that validate
    OVN-Kubernetes components on cluster nodes.
    """

    objective_hosts = [Objectives.ALL_NODES]

    def is_ovn(self):
        # Local import to avoid circular dependency (ovs_collectors imports OvsOperatorBase)

        is_ovn_data = self.run_data_collector(IsOVNKubernetesCollector)
        return next(iter(is_ovn_data.values()), False)

    def _run_ovn_rule(self) -> RuleResult:
        raise NotImplementedError("Subclasses must implement _run_ovn_rule() method")

    def run_rule(self):
        if not self.is_ovn():
            return RuleResult.not_applicable("Cluster is not using OVN-Kubernetes networking")
        return self._run_ovn_rule()

    def _check_link_state(self, interface_name: str) -> tuple[bool, str]:
        """
        Check if network interface exists and is UP.

        Args:
            interface_name: Interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip link show {iface}").format(iface=interface_name))

        if rc != 0:
            return False, f"{interface_name} interface does not exist: {err.strip()}"

        if "state UP" not in out and "state UNKNOWN" not in out:
            return False, f"{interface_name} interface is DOWN"

        return True, ""


class IsOVNKubernetesCollector(OrchestratorDataCollector):
    """
    Detect if cluster is using OVN-Kubernetes networking.

    Checks the cluster's network.operator/cluster CR to determine
    the network type. Used by node-level OVS rules to determine applicability.
    """

    objective_hosts = [Objectives.ORCHESTRATOR]

    def collect_data(self, **kwargs) -> bool:
        """
        Check cluster network type.

        Returns:
            True if OVN-Kubernetes, False otherwise
        """
        try:
            network_obj = self.oc_api.select_resources(resource_type="network.operator/cluster", single=True)
            if not network_obj:
                return False

            network_type = network_obj.model.spec.defaultNetwork.type
            return network_type == "OVNKubernetes"

        except Exception:
            return False


class NncpOvsBondVlanCollector(OvsOperatorBase, OrchestratorDataCollector):
    """
    Collect OVS bond VLAN names from NodeNetworkConfigurationPolicy resources.

    Queries NNCP (nmstate.io) resources from cluster API to identify which bond VLANs
    are intended for OVS/OVN datapath based on their configuration as OVS bridge ports.
    """

    unique_name = "nncp_ovs_bond_vlan_collector"

    def is_vlan_naming_pattern(self, interface_name: str) -> bool:
        """
        Check if interface name matches VLAN naming pattern.

        VLAN interfaces follow the format <parent>.<vlan_id> where vlan_id is numeric.

        Args:
            interface_name: Interface name to check

        Returns:
            True if interface name matches VLAN pattern, False otherwise
        """
        if "." not in interface_name:
            return False

        parts = interface_name.rsplit(".", 1)
        return len(parts) == 2 and parts[1].isdigit()

    def collect_data(self) -> set[str]:
        """
        Query NNCP resources and extract bond VLANs configured for OVS.

        Checks two NNCP patterns for OVS VLAN configuration:
        1. VLANs listed as ports within ovs-bridge definitions
        2. VLANs defined as separate ovs-port type interfaces

        Returns:
            Set of bond VLAN names (e.g., {'<bond>.<vlan_id>', '<bond>.<vlan_id>'})
            Empty set if no NNCP resources found or no OVS VLANs configured
        """
        try:
            nncps = self.oc_api.select_resources(
                "nodenetworkconfigurationpolicies.nmstate.io", timeout=60, all_namespaces=True
            )
        except Exception as e:
            self.logger.warning(f"Failed to query NNCP resources: {e}")
            return set()

        ovs_bond_vlans = set()

        for nncp in nncps:
            nncp_dict = nncp.as_dict()
            desired_state = nncp_dict.get("spec", {}).get("desiredState", {})
            interfaces = desired_state.get("interfaces", [])

            for iface in interfaces:
                iface_type = iface.get("type", "")
                iface_name = iface.get("name", "")

                # Pattern 1: VLANs listed as ports within ovs-bridge definition
                if iface_type == "ovs-bridge":
                    bridge_ports = iface.get("bridge", {}).get("port", [])
                    for port in bridge_ports:
                        port_name = port.get("name", "")
                        if self.is_vlan_naming_pattern(port_name):
                            ovs_bond_vlans.add(port_name)

                # Pattern 2: VLANs defined as separate ovs-port type entries
                elif iface_type == "ovs-port":
                    if self.is_vlan_naming_pattern(iface_name):
                        ovs_bond_vlans.add(iface_name)

        return ovs_bond_vlans


class OvnSecondaryNetworkBridgesCollector(OrchestratorDataCollector):
    """
    Identify OVN secondary network bridges from NodeNetworkConfigurationPolicy resources.

    Secondary network bridges (e.g., br-secondary1) are configured for OVN localnet mappings
    and may not require internal ports or IP addresses (pure L2 bridges for VM traffic).
    This collector identifies them so validation rules can apply appropriate checks.
    """

    unique_name = "ovn_secondary_network_bridges_collector"

    def collect_data(self) -> set[str]:
        """
        Query NNCP resources and extract OVN secondary network bridge names.

        Identifies bridges with OVN bridge-mappings (localnet configurations).
        These bridges are typically pure L2 bridges and don't need IP addressing.

        Returns:
            Set of secondary bridge names (e.g., {'br-secondary1', 'br-secondary2'})
            Empty set if no NNCP resources found or no secondary bridges configured
        """
        try:
            nncps = self.oc_api.select_resources(
                "nodenetworkconfigurationpolicies.nmstate.io", timeout=60, all_namespaces=True
            )
        except Exception as e:
            self.logger.warning(f"Failed to query NNCP resources: {e}")
            return set()

        secondary_bridges = set()

        for nncp in nncps:
            nncp_dict = nncp.as_dict()
            desired_state = nncp_dict.get("spec", {}).get("desiredState", {})

            # Check for OVN bridge-mappings (indicates secondary network bridge)
            ovn_config = desired_state.get("ovn", {})
            bridge_mappings = ovn_config.get("bridge-mappings", [])

            for mapping in bridge_mappings:
                bridge_name = mapping.get("bridge", "")
                localnet = mapping.get("localnet", "")

                # Only secondary networks (localnet != default physnet)
                # Primary bridge (br-ex) uses physnet for default overlay
                # Secondary bridges use localnet1, localnet2, etc.
                if bridge_name and localnet:
                    secondary_bridges.add(bridge_name)

        return secondary_bridges
