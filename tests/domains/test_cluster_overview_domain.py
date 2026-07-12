"""Tests for cluster overview domain."""

from in_cluster_checks.domains.cluster_overview_domain import ClusterOverviewDomain
from in_cluster_checks.rules.cluster_overview.architecture_overview import ClusterArchitectureOverview


def test_cluster_overview_domain_name():
    """Test domain name."""
    domain = ClusterOverviewDomain()
    assert domain.domain_name() == "cluster_overview"


def test_cluster_overview_domain_rules():
    """Test domain returns correct rules."""
    domain = ClusterOverviewDomain()
    rules = domain.get_rule_classes()

    assert len(rules) == 1
    assert ClusterArchitectureOverview in rules
