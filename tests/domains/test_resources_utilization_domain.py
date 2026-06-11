import pytest

from in_cluster_checks.domains.resources_utilization_domain import ResourcesUtilizationDomain
from in_cluster_checks.rules.resources_utilization.resources_utilization import ResourcesUtilization


class TestResourcesUtilizationDomain:
    """Test ResourcesUtilizationDomain."""

    def test_get_rule_classes(self):
        """Test domain returns correct rule classes."""
        domain = ResourcesUtilizationDomain()
        rule_classes = domain.get_rule_classes()

        assert ResourcesUtilization in rule_classes
        assert len(rule_classes) == 1

    def test_domain_name(self):
        """Test domain name contract."""
        domain = ResourcesUtilizationDomain()
        assert domain.domain_name() == "resources_utilization"
