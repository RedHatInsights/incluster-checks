"""
Cluster overview rule domain.

Collects informational, read-only snapshots describing what the cluster is
(architecture, versions, stack) rather than validating pass/fail conditions.
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.cluster_overview.architecture_overview import ClusterArchitectureOverview


class ClusterOverviewDomain(RuleDomain):
    """
    Cluster overview domain.

    Groups informational collection rules that describe the cluster's
    architecture: identity, topology, network, storage, and platform services.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "cluster_overview"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of cluster overview rules to run.

        Returns:
            List of Rule classes
        """
        return [
            ClusterArchitectureOverview,
        ]
