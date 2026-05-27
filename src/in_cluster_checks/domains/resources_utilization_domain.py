"""Resources Utilization domain for cluster resource reporting."""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.resources_utilization.resources_utilization import ResourcesUtilization


class ResourcesUtilizationDomain(RuleDomain):
    """Domain for cluster resources utilization data collection and reporting."""

    def domain_name(self) -> str:
        """Get domain name."""
        return "resources_utilization"

    def get_rule_classes(self) -> List[type]:
        """Get resources utilization domain rule classes.

        Returns:
            List containing ResourcesUtilization orchestrator rule.
        """
        return [ResourcesUtilization]
