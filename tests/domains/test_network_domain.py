"""
Tests for NetworkValidationDomain.
"""

from unittest.mock import Mock

import pytest

from in_cluster_checks.domains.network_domain import NetworkValidationDomain
from in_cluster_checks.rules.network.node_connectivity_validations import (
    AreAllNodesConnected,
    VerifyBondedInterfacesUp,
)
from in_cluster_checks.rules.network.ovnk8s_validations import (
    LogicalSwitchNodeValidator,
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


class TestNetworkRuleDomain:
    """Test NetworkValidationDomain."""

    def test_domain_name(self):
        """Test that domain_name returns correct value."""
        domain = NetworkValidationDomain()
        assert domain.domain_name() == "network"

    def test_get_rule_classes(self):
        """Test that get_rule_classes returns rule list."""
        domain = NetworkValidationDomain()
        rules = domain.get_rule_classes()

        assert isinstance(rules, list)
        assert len(rules) == 9
        assert OvsInterfaceAndPortFound in rules
        # assert Bond0DnsServersComparison in rules  # Commented out to match insights-on-prem
        assert AreAllNodesConnected in rules
        assert VerifyBondedInterfacesUp in rules
        assert NodesHaveOvnkubeNodePod in rules
        assert LogicalSwitchNodeValidator in rules
        assert WhereaboutsDuplicateIPAddresses in rules
        assert WhereaboutsMissingPodrefs in rules
        assert WhereaboutsMissingAllocations in rules
        assert WhereaboutsExistingAllocations in rules

    def test_verify_runs_validators(self):
        """Test that verify() runs validators on nodes."""
        domain = NetworkValidationDomain()

        # Create mock executor that returns valid nmcli output
        mock_executor = Mock()
        mock_executor.host_name = "test-node"
        mock_executor.ip = "192.168.1.10"
        mock_executor.roles = ["ALL_NODES"]  # Add roles for new pattern
        mock_executor.get_output_from_run_cmd.return_value = """ovs-if-phys  uuid1  ovs-interface  br-ex
ovs-port-phys  uuid2  ovs-port  bond0"""

        node_executors = {'test-node': mock_executor}

        result = domain.verify(node_executors)

        assert result['domain_name'] == 'network'
        assert 'details' in result
        assert 'test-node - 192.168.1.10' in result['details']

    def test_domain_inherits_from_validation_domain(self):
        """Test that NetworkValidationDomain inherits from RuleDomain."""
        from in_cluster_checks.core.domain import RuleDomain

        domain = NetworkValidationDomain()
        assert isinstance(domain, RuleDomain)
