"""
DPF (DPU Platform Framework) validation checks for OpenShift clusters
with NVIDIA BlueField DPUs.
"""

import re
from typing import Dict, List, Optional

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.core.rule import PrerequisiteResult, Rule, RuleResult
from in_cluster_checks.rules.network.bond_base import BondBase
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


class DpuBondLacpHealth(BondBase):
    """Verify LACP bond health on DPU ports.

    Checks that bond interfaces using 802.3ad (LACP) mode have all slave
    interfaces UP, are in the same aggregator, and are not in churned state.
    A degraded bond means traffic flows through a single port, reducing
    available bandwidth without any Kubernetes-visible failure.
    """

    objective_hosts = [Objectives.ALL_NODES]
    supported_profiles = {"dpf"}
    unique_name = "dpu_bond_lacp_health"
    title = "Verify LACP bond health on DPU ports"
    links = ["https://github.com/RedHatInsights/incluster-checks/wiki/DPF---LACP-bond-health-on-DPU-ports"]

    def _parse_bond_info(self, bond_name: str) -> Dict:
        """Parse /proc/net/bonding/<bond> for LACP-specific fields.

        Args:
            bond_name: Name of the bond interface.

        Returns:
            Dictionary with bond mode, MII status, and per-slave details.
        """
        bond_file = f"/proc/net/bonding/{bond_name}"
        lines = self.file_utils.get_lines_in_file(bond_file)
        if lines is None:
            return {"error": f"Cannot read bond {bond_name}"}

        content = "\n".join(lines)
        sections = [s.strip() for s in content.split("\n\n") if s.strip()]

        info: Dict = {"mode": "", "mii_status": "", "slaves": []}

        for section in sections:
            section_lines = [line.strip() for line in section.split("\n") if line.strip()]

            if any(line.startswith("Slave Interface:") for line in section_lines):
                slave = self._parse_slave_section(section_lines)
                if slave:
                    info["slaves"].append(slave)
            else:
                for line in section_lines:
                    if line.startswith("Bonding Mode:"):
                        info["mode"] = line.split(":", 1)[1].strip()
                    elif line.startswith("MII Status:"):
                        info["mii_status"] = line.split(":", 1)[1].strip()

        return info

    def _parse_slave_section(self, section_lines: List[str]) -> Optional[Dict]:
        """Parse a slave interface section.

        Args:
            section_lines: Lines from a slave section.

        Returns:
            Dictionary with slave details, or None if parsing fails.
        """
        slave: Dict = {
            "name": "",
            "mii_status": "",
            "speed": "",
            "aggregator_id": "",
            "actor_churn": "",
            "partner_churn": "",
        }

        for line in section_lines:
            if line.startswith("Slave Interface:"):
                slave["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("MII Status:"):
                slave["mii_status"] = line.split(":", 1)[1].strip()
            elif line.startswith("Speed:"):
                slave["speed"] = line.split(":", 1)[1].strip()
            elif line.startswith("Aggregator ID:"):
                slave["aggregator_id"] = line.split(":", 1)[1].strip()
            elif line.startswith("Actor Churn State:"):
                slave["actor_churn"] = line.split(":", 1)[1].strip()
            elif line.startswith("Partner Churn State:"):
                slave["partner_churn"] = line.split(":", 1)[1].strip()

        return slave if slave["name"] else None

    def run_rule(self) -> RuleResult:
        """Check LACP bond health on all bond interfaces."""
        bond_names_list = self.file_utils.list_files(self.BONDING_PATH)
        if bond_names_list is None:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd=f"ls {self.BONDING_PATH}",
                output="Failed to list bond interfaces",
            )

        bond_names = bond_names_list
        all_issues: List[str] = []
        all_passed: List[str] = []

        for bond_name in bond_names:
            info = self._parse_bond_info(bond_name)

            if "error" in info:
                all_issues.append(f"{bond_name}: {info['error']}")
                continue

            if "802.3ad" not in info["mode"]:
                continue

            if info["mii_status"] != "up":
                all_issues.append(f"{bond_name}: bond MII status is {info['mii_status']}")
                continue

            if len(info["slaves"]) < 2:
                all_issues.append(f"{bond_name}: only {len(info['slaves'])} slave(s), expected 2+ for LACP")
                continue

            down_slaves = [s for s in info["slaves"] if s["mii_status"] != "up"]
            if down_slaves:
                names = ", ".join(s["name"] for s in down_slaves)
                all_issues.append(f"{bond_name}: slave(s) down: {names}")

            missing_agg = [s["name"] for s in info["slaves"] if not s["aggregator_id"]]
            if missing_agg:
                all_issues.append(
                    f"{bond_name}: missing aggregator_id on slave(s): {', '.join(missing_agg)}, LACP not negotiated"
                )
            else:
                agg_ids = set(s["aggregator_id"] for s in info["slaves"])
                if len(agg_ids) > 1:
                    details = ", ".join(f"{s['name']}=agg{s['aggregator_id']}" for s in info["slaves"])
                    all_issues.append(
                        f"{bond_name}: slaves in different aggregators ({details}), LACP not fully negotiated"
                    )

            churned: List[str] = []
            for s in info["slaves"]:
                if s["actor_churn"] and s["actor_churn"] != "none":
                    churned.append(f"{s['name']} actor={s['actor_churn']}")
                if s["partner_churn"] and s["partner_churn"] != "none":
                    churned.append(f"{s['name']} partner={s['partner_churn']}")
            if churned:
                all_issues.append(f"{bond_name}: LACP churn detected: {', '.join(churned)}")

            if not down_slaves and not missing_agg and not churned:
                agg_ids = set(s["aggregator_id"] for s in info["slaves"])
                if len(agg_ids) == 1:
                    slave_info = ", ".join(f"{s['name']} ({s['speed']})" for s in info["slaves"])
                    all_passed.append(f"{bond_name}: LACP healthy, {len(info['slaves'])} slaves UP ({slave_info})")

        if not all_issues and not all_passed:
            return RuleResult.skip("No LACP (802.3ad) bonds found")

        if all_issues:
            msg = "LACP bond issues detected:\n" + "\n".join(f"  - {i}" for i in all_issues)
            if all_passed:
                msg += "\nHealthy bonds:\n" + "\n".join(f"  - {p}" for p in all_passed)
            return RuleResult.failed(msg)

        return RuleResult.passed("All LACP bonds healthy:\n" + "\n".join(f"  - {p}" for p in all_passed))


class OvnGeneveTunnelLocalIp(Rule):
    """Verify OVN Geneve tunnel local_ip matches the node's Kubernetes InternalIP.

    OVN programs Geneve tunnels between nodes using each node's IP as the
    local_ip in the tunnel options. If the node's IP changes (e.g. during
    interface migration) without a corresponding OVN restart, the tunnels
    retain the old local_ip, causing silent inter-node connectivity loss
    while the node remains Ready.
    """

    objective_hosts = [Objectives.ALL_NODES]
    supported_profiles = {"dpf"}
    unique_name = "ovn_geneve_tunnel_local_ip"
    title = "Verify OVN Geneve tunnel local_ip matches node InternalIP"
    links = ["https://github.com/RedHatInsights/incluster-checks/wiki/DPF---OVN-Geneve-tunnel-local_ip"]

    def _get_ovs_show(self) -> Optional[str]:
        """Run ovs-vsctl show and return output, or None on failure."""
        try:
            return self.get_output_from_run_cmd(SafeCmdString("ovs-vsctl show"))
        except Exception:
            return None

    def _extract_geneve_local_ips(self, ovs_output: str) -> List[str]:
        """Extract local_ip values only from Geneve tunnel interface blocks.

        Args:
            ovs_output: Output from ovs-vsctl show.

        Returns:
            Unique list of local_ip values found in Geneve interface blocks.
        """
        local_ips = []
        in_geneve_block = False
        for line in ovs_output.splitlines():
            stripped = line.strip()
            if stripped == "type: geneve":
                in_geneve_block = True
            elif stripped.startswith("type:"):
                in_geneve_block = False
            elif in_geneve_block and "local_ip=" in stripped:
                match = re.search(r'local_ip="([^"]+)"', stripped)
                if match and match.group(1) not in local_ips:
                    local_ips.append(match.group(1))
                in_geneve_block = False
        return local_ips

    def is_prerequisite_fulfilled(self) -> PrerequisiteResult:
        """Check if OVS has any Geneve tunnel interfaces."""
        ovs_output = self._get_ovs_show()
        if ovs_output is None:
            return PrerequisiteResult.not_met("Cannot access OVS")
        if "geneve" not in ovs_output:
            return PrerequisiteResult.not_met("No Geneve tunnels configured")
        return PrerequisiteResult.met()

    def _get_node_ip(self) -> Optional[str]:
        """Get this node's primary IP from the nodeip-configuration file."""
        try:
            content = self.file_utils.read_file("/run/nodeip-configuration/primary-ip")
            return content.strip() if content.strip() else None
        except UnExpectedSystemOutput:
            return None

    def run_rule(self) -> RuleResult:
        """Check that Geneve tunnel local_ip matches node InternalIP."""
        ovs_output = self._get_ovs_show()
        if ovs_output is None:
            raise UnExpectedSystemOutput(
                ip=self.get_host_ip(),
                cmd="ovs-vsctl show",
                output="Failed to run ovs-vsctl show",
            )

        local_ips = list(set(self._extract_geneve_local_ips(ovs_output)))
        if not local_ips:
            return RuleResult.skip("No Geneve local_ip found in OVS output")

        node_ip = self._get_node_ip()
        if not node_ip:
            return RuleResult.skip("Cannot determine node primary IP")

        if len(local_ips) > 1:
            return RuleResult.failed(
                f"Multiple different local_ip values in Geneve tunnels: {sorted(local_ips)}. "
                f"OVS configuration may be inconsistent."
            )

        geneve_local_ip = local_ips[0]
        if geneve_local_ip != node_ip:
            return RuleResult.failed(
                f"Geneve tunnel local_ip ({geneve_local_ip}) does not match "
                f"node primary IP ({node_ip}). "
                f"Inter-node pod connectivity may be broken."
            )

        return RuleResult.passed(f"Geneve tunnel local_ip ({geneve_local_ip}) matches node primary IP")
