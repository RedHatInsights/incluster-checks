"""
Network rule domain for OpenShift cluster.

Orchestrates network-related healthcheck validators.
Based on support/HealthChecks/flows/Network/network_flows_openshift.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.network.node_connectivity_validations import AreAllNodesConnected, VerifyBondedInterfacesUp
from in_cluster_checks.rules.network.ovnk8s_validations import (
    LogicalSwitchNodeValidator,
    MTUOverlayInterfaces,
    NodesHaveOvnkubeNodePod,
)
from in_cluster_checks.rules.network.ovs_validations import OvsInterfaceAndPortFound

# from in_cluster_checks.rules.network.ovs_validations import Bond0DnsServersComparison
from in_cluster_checks.rules.network.whereabouts_validations import (
    WhereaboutsDuplicateIPAddresses,
    WhereaboutsExistingAllocations,
    WhereaboutsMissingAllocations,
    WhereaboutsMissingPodrefs,
)


class NetworkValidationDomain(RuleDomain):
    """
    Network rule domain for OpenShift.

    Validates network health including OVS, OVN-Kubernetes, Whereabouts, and node connectivity.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "network"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of network validators to run.

        Returns:
            List of Rule classes
        """
        return [
            OvsInterfaceAndPortFound,
            # Bond0DnsServersComparison,
            AreAllNodesConnected,
            VerifyBondedInterfacesUp,
            NodesHaveOvnkubeNodePod,
            LogicalSwitchNodeValidator,
            MTUOverlayInterfaces,
            WhereaboutsDuplicateIPAddresses,
            WhereaboutsMissingPodrefs,
            WhereaboutsMissingAllocations,
            WhereaboutsExistingAllocations,
        ]
