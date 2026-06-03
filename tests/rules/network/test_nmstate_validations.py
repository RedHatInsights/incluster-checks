"""
Unit tests for NMState NodeNetworkConfigurationPolicy validators.

Tests for VerifyAllNNCPsAvailable rule.
"""

from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.network.nmstate_validations import VerifyAllNNCPsAvailable
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase


def _create_mock_nncp(
    name: str,
    available: str = "True",
    degraded: str = "False",
    progressing: str = "False",
):
    """Create mock NNCP object with status conditions."""
    mock_condition_available = Mock()
    mock_condition_available.type = "Available"
    mock_condition_available.status = available
    mock_condition_available.message = (
        "Successfully configured" if available == "True" else "Configuration failed"
    )

    mock_condition_degraded = Mock()
    mock_condition_degraded.type = "Degraded"
    mock_condition_degraded.status = degraded
    mock_condition_degraded.message = (
        "Degraded state detected" if degraded == "True" else "Not degraded"
    )

    mock_condition_progressing = Mock()
    mock_condition_progressing.type = "Progressing"
    mock_condition_progressing.status = progressing
    mock_condition_progressing.message = (
        "Configuration in progress" if progressing == "True" else "Not progressing"
    )

    mock_nncp = Mock()
    mock_nncp.model.metadata.name = name
    mock_nncp.model.status.conditions = [
        mock_condition_available,
        mock_condition_degraded,
        mock_condition_progressing,
    ]

    return mock_nncp


class TestVerifyAllNNCPsAvailable(RuleTestBase):
    """Tests for VerifyAllNNCPsAvailable rule."""

    tested_type = VerifyAllNNCPsAvailable

    # Prerequisite scenarios
    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "NMState operator not installed - CRD not found",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(side_effect=Exception("no matches for kind"))
                )
            },
        ),
        RuleScenarioParams(
            "NNCP resource not found",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        side_effect=Exception(
                            "nodenetworkconfigurationpolicies.nmstate.io not found"
                        )
                    )
                )
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "NMState operator installed - CRD exists",
            tested_object_mock_dict={
                "oc_api": Mock(select_resources=Mock(return_value=[]))
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_not_fulfilled(
            self, scenario_params, tested_object
        )

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    # Test scenarios - PASSED
    scenario_passed = [
        RuleScenarioParams(
            "all NNCPs are healthy",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("br-ex-nncp"),
                            _create_mock_nncp("worker-bond-nncp"),
                        ]
                    )
                )
            },
        ),
        RuleScenarioParams(
            "single NNCP is healthy",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("br-ex-nncp"),
                        ]
                    )
                )
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    # Test scenarios - FAILED
    scenario_failed = [
        RuleScenarioParams(
            "NNCP not available",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("br-ex-nncp", available="False"),
                        ]
                    )
                )
            },
            failed_msg="NodeNetworkConfigurationPolicies are not healthy:\n  - br-ex-nncp: Not Available (Configuration failed)",
        ),
        RuleScenarioParams(
            "NNCP degraded",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("worker-bond-nncp", degraded="True"),
                        ]
                    )
                )
            },
            failed_msg="NodeNetworkConfigurationPolicies are not healthy:\n  - worker-bond-nncp: Degraded (Degraded state detected)",
        ),
        RuleScenarioParams(
            "NNCP still progressing",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("br-ex-nncp", progressing="True"),
                        ]
                    )
                )
            },
            failed_msg="NodeNetworkConfigurationPolicies are not healthy:\n  - br-ex-nncp: Still Progressing (Configuration in progress)",
        ),
        RuleScenarioParams(
            "multiple NNCPs with different issues",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            _create_mock_nncp("br-ex-nncp", available="False"),
                            _create_mock_nncp("worker-bond-nncp", degraded="True"),
                            _create_mock_nncp("vlan-nncp", progressing="True"),
                        ]
                    )
                )
            },
            failed_msg=(
                "NodeNetworkConfigurationPolicies are not healthy:\n"
                "  - br-ex-nncp: Not Available (Configuration failed)\n"
                "  - worker-bond-nncp: Degraded (Degraded state detected)\n"
                "  - vlan-nncp: Still Progressing (Configuration in progress)"
            ),
        ),
        RuleScenarioParams(
            "NNCP with no conditions",
            tested_object_mock_dict={
                "oc_api": Mock(
                    select_resources=Mock(
                        return_value=[
                            Mock(
                                **{
                                    "model.metadata.name": "broken-nncp",
                                    "model.status.conditions": None,
                                }
                            )
                        ]
                    )
                )
            },
            failed_msg="NodeNetworkConfigurationPolicies are not healthy:\n  - broken-nncp: No status conditions found",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)

    # Test scenarios - NOT APPLICABLE
    scenario_not_applicable = [
        RuleScenarioParams(
            "no NNCPs found",
            tested_object_mock_dict={
                "oc_api": Mock(select_resources=Mock(return_value=[]))
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_not_applicable)
    def test_scenario_not_applicable(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_not_applicable(self, scenario_params, tested_object)
