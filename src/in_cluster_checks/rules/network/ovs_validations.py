"""
OVS (Open vSwitch) network validations.

Ported from support/HealthChecks/flows/Network/ovs_validations.py
"""

import re

from in_cluster_checks.core.rule import PrerequisiteResult, RuleResult
from in_cluster_checks.rules.network.ovs_base import (
    NncpOvsBondVlanCollector,
    OvnDetectingNodeRuleBase,
    OvnSecondaryNetworkBridgesCollector,
)
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class VlanOvsAttachmentCheck(OvnDetectingNodeRuleBase):
    """
    Verify OVS-configured VLAN interfaces are attached to OVS bridge.

    Identifies OVS VLANs from two sources and validates they're attached to the bridge:
    1. NodeNetworkConfigurationPolicy (NNCP) - cluster-wide declarative configuration
    2. NetworkManager profiles - VLANs configured manually or at install time

    Only checks VLAN interfaces explicitly configured for OVS (ovs-port type).
    Handles all VLAN types: <bond>.<vlan_id>, <team>.<vlan_id>, <ethernet>.<vlan_id>.
    VLANs for storage networks, BMC, SR-IOV, or external systems are excluded.

    RCA symptom: "VLAN interface is removed from the bridge. This means it is
                  no longer managed by OVS"
    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "vlan_ovs_attachment_check"
    title = "Verify OVS-configured VLAN interfaces are attached to OVS bridge"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-VLAN-OVS-Attachment-Check",
    ]

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """
        Check if VLAN interfaces exist on this node.

        Returns:
            PrerequisiteResult indicating if VLANs are present
        """
        vlan_interfaces = self._get_active_vlan_connections()
        if not vlan_interfaces:
            return PrerequisiteResult.not_met("No VLAN interfaces found on this node")

        return PrerequisiteResult.met()

    def _get_network_manager_ovs_vlans(self) -> set[str]:
        """
        Query active NetworkManager profiles to find VLANs configured for OVS.

        Queries active NetworkManager connection profiles to identify VLANs
        configured as ovs-port type. This catches VLANs configured manually
        or at install time (not managed by NNCP).

        Inactive ovs-port profiles are detected by OvsProfileActivationCheck instead.

        Returns:
            Set of active VLAN device names with TYPE=ovs-port
            Example: {'<bond>.<vlan_id>', '<bond>.<vlan_id>'}
            Empty set if no active ovs-port VLANs found
        """
        # Query only ACTIVE connections for TYPE and DEVICE
        connections = self._get_nmcli_connections(SafeCmdString("TYPE,DEVICE"), is_active=True)

        # Get all VLAN interfaces once (optimization)
        vlan_interfaces = self._list_proc_vlan_interfaces()

        ovs_vlans = set()
        for conn in connections:
            conn_type = conn.get("TYPE", "")
            device = conn.get("DEVICE", "")

            # Filter for ovs-port type with VLAN interface name (check membership in cached set)
            if conn_type == "ovs-port" and device in vlan_interfaces:
                ovs_vlans.add(device)

        return ovs_vlans

    def _run_ovn_rule(self) -> RuleResult:
        """
        Check if OVS-configured VLAN interfaces are attached to OVS on this node.

        Combines NNCP and NetworkManager data to identify all OVS VLANs on this node,
        then validates they are properly attached to the OVS bridge.

        Returns:
            RuleResult indicating VLAN attachment status
        """
        vlans_to_check = self._get_expected_ovs_vlans()

        if not vlans_to_check:
            return RuleResult.not_applicable(
                "No VLAN interfaces configured for OVS (checked NNCP and NetworkManager profiles)"
            )

        return self._validate_vlans_in_ovs(vlans_to_check)

    def _get_expected_ovs_vlans(self) -> list[str]:
        """
        Get VLANs that should be in OVS on this node (from NNCP and NetworkManager).

        Combines VLANs from both sources to handle hybrid scenarios:
        - VLANs configured in NNCP (cluster-wide declarative config)
        - VLANs configured manually or at install time (via NetworkManager)

        Returns:
            List of VLAN names expected to be in OVS on this node
        """
        all_vlans = set()

        # Method 1: Query NNCP (cluster-wide declarative configuration)
        nncp_data = self.run_data_collector(NncpOvsBondVlanCollector)
        nncp_vlans = next(iter(nncp_data.values()), set())

        if nncp_vlans:
            # NNCP returns cluster-wide VLANs, filter to only those on this node
            vlans_on_node = self._get_active_vlan_connections()
            nncp_vlans_on_node = {v for v in nncp_vlans if v in vlans_on_node}
            all_vlans.update(nncp_vlans_on_node)

        # Method 2: Query NetworkManager (node-local active connections)
        # Always check NetworkManager to catch VLANs configured outside NNCP
        nm_vlans = self._get_network_manager_ovs_vlans()
        if nm_vlans:
            all_vlans.update(nm_vlans)

        if not all_vlans:
            return []

        return list(all_vlans)

    def _validate_vlans_in_ovs(self, vlans_to_check: list[str]) -> RuleResult:
        """
        Validate that VLANs are attached to OVS bridges.

        Checks ALL bridges with physical ports in multi-bridge setups.

        Args:
            vlans_to_check: VLANs that should be in OVS

        Returns:
            RuleResult indicating validation status
        """
        # Get all bridges and their ports
        bridges_and_ports = self._get_external_ovs_bridges()
        if not bridges_and_ports:
            return RuleResult.failed(
                "VLAN interfaces exist but no OVS bridges found - OVS may not be configured properly"
            )

        # Collect all ports across all bridges
        vlans_in_ovs = []
        for bridge_info in bridges_and_ports.values():
            vlans_in_ovs.extend(bridge_info["all_ports"])

        detached_vlans = [vlan for vlan in vlans_to_check if vlan not in vlans_in_ovs]

        if detached_vlans:
            # Add context about which bridges were checked
            bridges = list(bridges_and_ports.keys())
            if len(bridges) > 1:
                bridge_list = ", ".join(bridges)
                return RuleResult.failed(
                    f"OVS-configured VLAN interface(s) detached from OVS bridges "
                    f"(checked {bridge_list}): {', '.join(detached_vlans)}"
                )
            else:
                return RuleResult.failed(
                    f"OVS-configured VLAN interface(s) detached from OVS bridge: {', '.join(detached_vlans)}"
                )

        # Success message
        bridges = list(bridges_and_ports.keys())
        vlan_list = ", ".join(sorted(vlans_to_check))

        if len(bridges) > 1:
            bridge_list = ", ".join(bridges)
            return RuleResult.passed(
                f"All {len(vlans_to_check)} OVS-configured VLAN interface(s) properly attached "
                f"across {len(bridges)} bridges ({bridge_list}): {vlan_list}"
            )
        else:
            return RuleResult.passed(
                f"All {len(vlans_to_check)} OVS-configured VLAN interface(s) properly attached to OVS: {vlan_list}"
            )

    def _get_active_vlan_connections(self) -> list[str]:
        """
        Get active VLAN connections from NetworkManager on this node.

        Uses: nmcli -t -f NAME,DEVICE connection show --active
        Filters by actual VLANs from /proc/net/vlan/

        Detects all VLAN interfaces (<bond>.<vlan_id>, <ethernet>.<vlan_id>, <team>.<vlan_id>, etc.)
        in format <parent>.<vlan_id> where vlan_id is numeric.

        Returns:
            List of VLAN device names (e.g., ['<bond>.<vlan_id>', '<ethernet>.<vlan_id>', '<team>.<vlan_id>'])
            Empty list if none found or on error
        """
        connections = self._get_nmcli_connections(SafeCmdString("NAME,DEVICE"), is_active=True)
        vlan_interfaces = self._list_proc_vlan_interfaces()  # Single ls command instead of N test commands
        return [conn["DEVICE"] for conn in connections if conn["DEVICE"] in vlan_interfaces]


class OvsInterfaceAndPortFound(OvnDetectingNodeRuleBase):
    """
    Verify that OVS interface and port are managed by NetworkManager (OVN-Kubernetes only).

    Checks for NetworkManager connections with types:
    - ovs-interface: OVS bridge interface (present in all OVN-K8s deployments)
    - ovs-port: OVS port (present in all OVN-K8s deployments)

    Works for both standard installer deployments and bare-metal with bonding.

    """

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "ovs_interface_and_port_managed_by_network_manager"
    title = "Verify that ovs interface and port are managed by network manager"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-OVS-Interface-And-Port-Found",
    ]

    def _run_ovn_rule(self):
        """
        Run rule check.

        Returns:
            RuleResult indicating OVS interface and port status
        """

        # Get all connection types (active and inactive)
        connections = self._get_nmcli_connections(SafeCmdString("TYPE"), is_active=False)
        connection_types = {conn["TYPE"] for conn in connections}

        # Check for OVS connection types (works for both deployment types)
        has_ovs_interface = "ovs-interface" in connection_types
        has_ovs_port = "ovs-port" in connection_types

        missing_items = []
        if not has_ovs_interface:
            missing_items.append("No ovs-interface type connection found in NetworkManager")

        if not has_ovs_port:
            missing_items.append("No ovs-port type connection found in NetworkManager")

        if missing_items:
            return RuleResult.failed(".\n".join(missing_items) + ".")

        return RuleResult.passed()


class OvsPhysicalPortHealthCheck(OvnDetectingNodeRuleBase):
    """
    Verify OVS physical port is UP and correctly configured (OVN-Kubernetes only).

    Validates that the physical network port attached to OVS external bridge:
    - Exists and is attached to external bridge (br-ex)
    - Link state is UP
    - Has NO IP address (OVS ports forward traffic, bridge has IPs)

    Physical ports in OVS should NOT have IP addresses - they are just
    forwarding interfaces. The IP addressing is on the bridge (br-ex).

    Supports all physical port types: bonded interfaces,
    ethernet interfaces, or named interfaces.

    """

    unique_name = "ovs_physical_port_health_check"
    title = "Verify OVS physical port is UP and has no IP"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-OVS-Physical-Port-Health-Check",
    ]

    def _run_ovn_rule(self) -> RuleResult:
        """
        Check OVS physical port health on this node.

        Validates ALL physical ports across ALL bridges in multi-bridge setups.

        Returns:
            RuleResult indicating port health status
        """
        # Get all bridges and their physical ports
        bridges_and_ports = self._get_external_ovs_bridges()
        if not bridges_and_ports:
            return RuleResult.failed("No OVS bridges with physical ports found")

        # Check all physical ports across all bridges
        failed_ports = []
        total_ports = 0

        for bridge, ports_info in bridges_and_ports.items():
            physical_ports = ports_info["physical_ports"]
            for port_name in physical_ports:
                total_ports += 1

                # Check link state
                link_ok, link_msg = self._check_link_state(port_name)
                if not link_ok:
                    if len(bridges_and_ports) > 1:
                        failed_ports.append(f"{link_msg} (on bridge {bridge})")
                    else:
                        failed_ports.append(f"{link_msg}")
                    continue

                # Verify no IP address
                ip_ok, ip_msg = self._check_no_ip_address(port_name)
                if not ip_ok:
                    if len(bridges_and_ports) > 1:
                        failed_ports.append(f"{ip_msg} (on bridge {bridge})")
                    else:
                        failed_ports.append(f"{ip_msg}")

        if failed_ports:
            return RuleResult.failed("Physical port issues:\n" + "\n".join(failed_ports))

        # Build success message
        all_ports = []
        for ports_info in bridges_and_ports.values():
            all_ports.extend(ports_info["physical_ports"])

        port_list = ", ".join(all_ports)

        if len(bridges_and_ports) > 1:
            bridge_list = ", ".join(bridges_and_ports.keys())
            return RuleResult.passed(
                f"All {total_ports} OVS physical port(s) are UP with correct configuration "
                f"across {len(bridges_and_ports)} bridges ({bridge_list}): {port_list}"
            )
        else:
            return RuleResult.passed(
                f"All {total_ports} OVS physical port(s) are UP with correct configuration (no IP): {port_list}"
            )

    def _check_no_ip_address(self, port_name: str) -> tuple[bool, str]:
        """
        Verify physical port has NO IPv4 address.

        Physical OVS ports should only forward traffic, not have IPs.
        Link-local IPv6 addresses (fe80::) are acceptable.

        Args:
            port_name: Port interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip addr show {iface}").format(iface=port_name))

        if rc != 0:
            return False, f"Cannot query {port_name} addressing: {err.strip()}"

        # Check for IPv4 address (should NOT exist on physical port)
        if "inet " in out:
            ip_match = re.search(r"inet (\S+)", out)
            ip_addr = ip_match.group(1) if ip_match else "unknown"
            return False, (
                f"{port_name} has IP address {ip_addr} - physical OVS ports should not have IPs "
                f"(IPs belong on the bridge interface)"
            )

        return True, ""


class OvsBridgeInterfaceHealthCheck(OvnDetectingNodeRuleBase):
    """
    Verify OVS bridge is UP and has proper OVN IP configuration.

    Validates OVS bridge (br-ex) health:
    - Bridge interface exists in NetworkManager
    - Link state is UP
    - Link-local IP address is assigned (169.254.x.x)

    For secondary network bridges (e.g., br-secondary1 configured for OVN localnet):
    - Only checks that the bridge exists in OVS
    - Skips internal port and IP validation (pure L2 bridges don't need IPs)

    The bridge is where OVN assigns IPs, not the physical ports.
    Different OVN deployments use different link-local subnets within
    the 169.254.0.0/16 range (both 169.254.169.x/29 and 169.254.0.x/17
    are valid OVN configurations).
    """

    unique_name = "ovs_bridge_interface_health_check"
    title = "Verify OVS bridge is UP with OVN link-local IP"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-OVS-Bridge-Interface-Health-Check",
    ]

    def _run_ovn_rule(self) -> RuleResult:
        """
        Check OVS bridge health on this node.

        Validates bridges with physical ports. Primary bridges (br-ex) must have
        internal ports and link-local IPs. Secondary network bridges are validated
        less strictly (OVS existence only).

        Returns:
            RuleResult indicating bridge health status
        """
        # Get all bridges with physical ports
        bridges_and_ports = self._get_external_ovs_bridges()
        if not bridges_and_ports:
            return RuleResult.failed("No OVS external bridges found")

        # Identify secondary network bridges (configured for OVN localnet)
        secondary_bridges_data = self.run_data_collector(OvnSecondaryNetworkBridgesCollector)
        secondary_bridges = next(iter(secondary_bridges_data.values()), set())

        # Validate each bridge
        failed_bridges = []
        secondary_bridges_checked = []

        for bridge_name in bridges_and_ports.keys():
            if bridge_name in secondary_bridges:
                # Secondary network bridges - just verify existence in OVS
                secondary_bridges_checked.append(bridge_name)
                continue

            # Primary bridge - strict validation
            error_msg = self._validate_primary_bridge_health(bridge_name)
            if error_msg:
                failed_bridges.append(error_msg)

        if failed_bridges:
            if len(bridges_and_ports) > 1:
                return RuleResult.failed(
                    f"Bridge interface issues (checked {len(bridges_and_ports)} bridges):\n" + "\n".join(failed_bridges)
                )
            return RuleResult.failed(f"Bridge interface issue: {failed_bridges[0]}")

        # Build success message
        primary_bridges = [b for b in bridges_and_ports.keys() if b not in secondary_bridges]
        return self._build_success_message(primary_bridges, secondary_bridges_checked)

    def _validate_primary_bridge_health(self, bridge_name: str) -> str:
        """
        Validate primary bridge link state and IP addressing.

        Args:
            bridge_name: Bridge name to validate

        Returns:
            Error message if validation fails, empty string if successful
        """
        # Check link state
        link_ok, link_msg = self._check_link_state(bridge_name)
        if not link_ok:
            return self._diagnose_missing_bridge_interface(bridge_name, link_msg)

        # Check IP addressing
        addr_ok, addr_msg = self._check_bridge_addressing(bridge_name)
        if not addr_ok:
            return addr_msg

        return ""

    def _diagnose_missing_bridge_interface(self, bridge_name: str, link_msg: str) -> str:
        """
        Diagnose why bridge interface doesn't exist.

        Args:
            bridge_name: Bridge name
            link_msg: Error message from link state check

        Returns:
            Detailed diagnostic error message
        """
        if "does not exist" not in link_msg.lower():
            return link_msg

        # Bridge interface doesn't exist - check OVS datapath
        if not self._is_ovs_datapath_accessible():
            return (
                f"{bridge_name} interface does not exist and cannot check OVS datapath "
                f"(ovs-appctl dpif/show failed). This may indicate OVS is not running properly."
            )

        # Check for internal port in OVS datapath
        has_internal_port = self._check_bridge_has_internal_port(bridge_name)
        if not has_internal_port:
            return (
                f"{bridge_name} exists in OVS database but missing internal port "
                f"(kernel interface not created). Bridge has ports in OVS but NetworkManager "
                f"failed to create the internal port. Check 'ovs-appctl dpif/show' and "
                f"NetworkManager logs for activation errors."
            )

        # Has internal port but still no kernel interface - unexpected
        return f"{link_msg} (unexpected: OVS datapath shows internal port exists)"

    def _build_success_message(self, primary_bridges: list[str], secondary_bridges: list[str]) -> RuleResult:
        """
        Build success message based on bridge types validated.

        Args:
            primary_bridges: List of primary bridge names
            secondary_bridges: List of secondary bridge names

        Returns:
            RuleResult with appropriate success message
        """
        if secondary_bridges:
            # Mixed setup or secondary only
            if primary_bridges:
                primary_list = ", ".join(primary_bridges)
                secondary_list = ", ".join(secondary_bridges)
                return RuleResult.passed(
                    f"Primary OVS bridge(s) are UP with proper OVN link-local IPs: {primary_list}. "
                    f"Secondary network bridge(s) exist in OVS: {secondary_list}"
                )
            # Only secondary bridges
            secondary_list = ", ".join(secondary_bridges)
            return RuleResult.passed(f"Secondary network bridge(s) exist in OVS: {secondary_list}")

        # Only primary bridges
        if len(primary_bridges) > 1:
            bridge_list = ", ".join(primary_bridges)
            return RuleResult.passed(
                f"All {len(primary_bridges)} OVS bridges are UP with proper OVN link-local IPs: {bridge_list}"
            )
        return RuleResult.passed(f"OVS bridge {primary_bridges[0]} is UP with proper OVN link-local IP")

    def _is_ovs_datapath_accessible(self) -> bool:
        """
        Check if we can query OVS datapath information.

        Returns:
            True if ovs-appctl dpif/show succeeds, False otherwise
        """
        rc, _, _ = self.run_cmd(SafeCmdString("ovs-appctl dpif/show"))
        return rc == 0

    def _check_bridge_has_internal_port(self, bridge_name: str) -> bool:
        """
        Check if OVS bridge has an internal port in the datapath.

        An OVS system bridge needs an internal port to create the kernel network interface.
        Without it, the bridge exists in the OVS database but has no kernel device.

        Args:
            bridge_name: Bridge name to check

        Returns:
            True if bridge has internal port, False otherwise
        """
        rc, out, _ = self.run_cmd(SafeCmdString("ovs-appctl dpif/show"))
        if rc != 0:
            return False

        # Parse dpif/show output to find bridge section and check for internal port
        # Format:
        #   br-ex:
        #     bond0 1/5: (system)
        #     br-ex 65534/6: (internal)  <- internal port
        #     patch-... 2/none: (patch: ...)

        in_bridge_section = False
        for line in out.splitlines():
            line = line.strip()

            # Detect bridge section start - use exact match to avoid false positives
            # (e.g., don't match "test-br:" when looking for "br:")
            if line == f"{bridge_name}:":
                in_bridge_section = True
                continue

            # Detect next bridge section (any line ending with ":")
            if in_bridge_section and line.endswith(":"):
                break  # Moved to next bridge, stop searching

            # Check for internal port within bridge section
            # Internal ports are named after the bridge (e.g., "br-ex 65534/6: (internal)")
            if in_bridge_section and "(internal)" in line and f"{bridge_name} " in line:
                return True

        return False

    def _check_bridge_addressing(self, bridge_name: str) -> tuple[bool, str]:
        """
        Verify bridge has link-local IP address (169.254.0.0/16).

        Different OVN deployments use different subnets within the
        169.254.0.0/16 link-local range. Both 169.254.169.x/29 and
        169.254.0.x/17 are valid configurations.

        Args:
            bridge_name: Bridge interface name to check

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        rc, out, err = self.run_cmd(SafeCmdString("ip addr show {iface}").format(iface=bridge_name))

        if rc != 0:
            return False, f"Cannot query {bridge_name} addressing: {err.strip()}"

        # Check for IPv4 address
        if "inet " not in out:
            return False, f"{bridge_name} has no IP address (OVN not initialized)"

        # Extract all IPv4 addresses and check if any are in link-local range (169.254.0.0/16)
        ipv4_addresses = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out)

        has_link_local = False
        for ip_str in ipv4_addresses:
            octets = ip_str.split(".")
            # Check if IP is in 169.254.0.0/16 range
            if len(octets) == 4 and octets[0] == "169" and octets[1] == "254":
                has_link_local = True
                break

        if not has_link_local:
            ip_match = re.search(r"inet (\S+)", out)
            ip_addr = ip_match.group(1) if ip_match else "unknown"
            return False, (
                f"{bridge_name} has unexpected IP addressing ({ip_addr}) - "
                f"expected 169.254.x.x (link-local) for OVN"
            )

        return True, ""


class OvsProfileActivationCheck(OvnDetectingNodeRuleBase):
    """
    Verify OVS-related NetworkManager profiles are activated (OVN-Kubernetes only).

    Checks for NetworkManager profiles with types ovs-port, ovs-interface, or
    ovs-bridge that exist but are in deactivated state. Inactive profiles indicate
    interfaces that should be part of OVS but failed to activate, which can cause
    network connectivity issues.

    This is a more reliable indicator than checking only active state, as it
    detects configuration that exists but failed to apply.

    """

    unique_name = "ovs_profile_activation_check"
    title = "Verify OVS NetworkManager profiles are activated"
    links = [
        "https://github.com/sprizend-rh/in-cluster-checks/wiki/Network-%E2%80%90-OVS-Profile-Activation-Check",
    ]

    def _run_ovn_rule(self) -> RuleResult:
        """
        Check for inactive OVS profiles on this node.

        Returns:
            RuleResult indicating profile activation status
        """
        # Query all OVS-related profiles with their activation state
        connections = self._get_nmcli_connections(SafeCmdString("TYPE,DEVICE,STATE"), is_active=False)

        # Filter for OVS types
        ovs_types = {"ovs-port", "ovs-interface", "ovs-bridge"}
        ovs_profiles = [conn for conn in connections if conn.get("TYPE") in ovs_types]

        if not ovs_profiles:
            return RuleResult.not_applicable("No OVS NetworkManager profiles found on this node")

        # Find inactive profiles
        # STATE can be: activated, deactivated, activating, deactivating
        inactive_profiles = []
        for profile in ovs_profiles:
            state = profile.get("STATE", "").lower()
            if state not in ("activated", "activating"):
                inactive_profiles.append(
                    {"device": profile.get("DEVICE", "unknown"), "type": profile.get("TYPE", "unknown"), "state": state}
                )

        if inactive_profiles:
            error_msg = self._build_inactive_profiles_message(inactive_profiles, ovs_profiles)
            return RuleResult.failed(error_msg)

        return RuleResult.passed(f"All {len(ovs_profiles)} OVS NetworkManager profile(s) are activated")

    def _build_inactive_profiles_message(self, inactive_profiles: list[dict], all_profiles: list[dict]) -> str:
        """
        Build formatted error message for inactive OVS profiles.

        Args:
            inactive_profiles: List of inactive profile dicts
            all_profiles: List of all OVS profile dicts

        Returns:
            Formatted error message
        """
        msg_parts = [
            f"Found {len(inactive_profiles)} inactive OVS profile(s) out of {len(all_profiles)} total.",
            "Inactive OVS profiles indicate interfaces that should be in OVS but failed to activate.",
            "",
            "Inactive profiles:",
        ]

        for profile in inactive_profiles:
            msg_parts.append(f"  - {profile['device']} (type: {profile['type']}, state: {profile['state']})")

        return "\n".join(msg_parts)
