"""
Tests for SR-IOV Network Operator validations.
"""

import json
from unittest.mock import Mock

import pytest

from in_cluster_checks.rules.network.sriov_validations import VerifySriovOperatorConfigured
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleScenarioParams, RuleTestBase

NAMESPACE = VerifySriovOperatorConfigured.SRIOV_NAMESPACE
CONFIG_NAME = VerifySriovOperatorConfigured.SRIOV_OPERATOR_CONFIG_NAME
SUBSCRIPTION_NAME = VerifySriovOperatorConfigured.operator_subscription_name


def create_mock_pod(namespace, name, phase, all_containers_ready=True):
    """Create a mock pod object."""
    mock_pod = Mock()
    mock_pod.as_dict.return_value = {
        "metadata": {"namespace": namespace, "name": name},
        "status": {
            "phase": phase,
            "containerStatuses": [{"ready": all_containers_ready}],
        },
    }
    return mock_pod


def _create_mock_sriov_operator_config(manage_software_bridges=True):
    """Create a mock SriovOperatorConfig resource object."""
    mock_config = Mock()
    mock_config.as_dict.return_value = {
        "spec": {"featureGates": {"manageSoftwareBridges": manage_software_bridges}},
    }
    return mock_config


def _sriov_subscriptions(include_sriov=True, include_ovs_cni_env=True):
    """Build a subscriptions response, optionally including the SR-IOV subscription."""
    items = []
    if include_sriov:
        spec = {"name": SUBSCRIPTION_NAME, "source": "redhat-operators"}
        if include_ovs_cni_env:
            spec["config"] = {
                "env": [{"name": "OVS_CNI_IMAGE", "value": "nvcr.io/nvidia/mellanox/ovs-cni-plugin:v1"}]
            }
        items.append(
            {
                "metadata": {"name": f"{SUBSCRIPTION_NAME}-subscription", "namespace": NAMESPACE},
                "spec": spec,
            }
        )
    items.append(
        {
            "metadata": {"name": "other-operator", "namespace": "openshift-operators"},
            "spec": {"name": "other", "source": "redhat-operators"},
        }
    )
    return {"items": items}


SUBSCRIPTIONS_OC_CMD = (
    "get",
    ("subscriptions.operators.coreos.com", "--all-namespaces", "-o", "json"),
)


class TestVerifySriovOperatorConfigured(RuleTestBase):
    """Test VerifySriovOperatorConfigured rule."""

    tested_type = VerifySriovOperatorConfigured

    scenario_passed = [
        RuleScenarioParams(
            "SriovOperatorConfig valid, pods healthy, OVS-CNI override present",
            tested_object_mock_dict={
                "oc_api.select_single_resource": Mock(return_value=_create_mock_sriov_operator_config()),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(NAMESPACE, "sriov-network-operator-abc123", "Running"),
                        create_mock_pod(NAMESPACE, "network-resources-injector-xyz789", "Running"),
                    ]
                ),
            },
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions())),
            },
        ),
    ]

    scenario_prerequisite_not_fulfilled = [
        RuleScenarioParams(
            "SR-IOV operator subscription not found",
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions(include_sriov=False))),
            },
        ),
    ]

    scenario_prerequisite_fulfilled = [
        RuleScenarioParams(
            "SR-IOV operator subscription found",
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions())),
            },
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "SriovOperatorConfig not found",
            tested_object_mock_dict={
                "oc_api.select_single_resource": Mock(return_value=None),
                "oc_api.get_all_pods": Mock(
                    return_value=[create_mock_pod(NAMESPACE, "sriov-network-operator-abc123", "Running")]
                ),
            },
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions())),
            },
            failed_msg=f"SriovOperatorConfig/{CONFIG_NAME} not found in {NAMESPACE} namespace",
        ),
        RuleScenarioParams(
            "manageSoftwareBridges feature gate disabled",
            tested_object_mock_dict={
                "oc_api.select_single_resource": Mock(
                    return_value=_create_mock_sriov_operator_config(manage_software_bridges=False)
                ),
                "oc_api.get_all_pods": Mock(
                    return_value=[create_mock_pod(NAMESPACE, "sriov-network-operator-abc123", "Running")]
                ),
            },
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions())),
            },
            failed_msg=f"SriovOperatorConfig/{CONFIG_NAME} has the manageSoftwareBridges feature gate disabled",
        ),
        RuleScenarioParams(
            "operator pod not ready",
            tested_object_mock_dict={
                "oc_api.select_single_resource": Mock(return_value=_create_mock_sriov_operator_config()),
                "oc_api.get_all_pods": Mock(
                    return_value=[
                        create_mock_pod(
                            NAMESPACE, "sriov-network-operator-abc123", "Running", all_containers_ready=False
                        )
                    ]
                ),
            },
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions())),
            },
            failed_msg=f"Unhealthy pods in {NAMESPACE} namespace:\n"
            "  sriov-network-operator-abc123 - Running, Not all containers ready",
        ),
        RuleScenarioParams(
            "OVS-CNI subscription override missing",
            tested_object_mock_dict={
                "oc_api.select_single_resource": Mock(return_value=_create_mock_sriov_operator_config()),
                "oc_api.get_all_pods": Mock(
                    return_value=[create_mock_pod(NAMESPACE, "sriov-network-operator-abc123", "Running")]
                ),
            },
            oc_cmd_output_dict={
                SUBSCRIPTIONS_OC_CMD: CmdOutput(json.dumps(_sriov_subscriptions(include_ovs_cni_env=False))),
            },
            failed_msg=f"Subscription/{SUBSCRIPTION_NAME} is missing the OVS_CNI_IMAGE environment variable override",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_fulfilled)
    def test_prerequisite_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is met when the SR-IOV operator subscription is installed."""
        RuleTestBase.test_prerequisite_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_prerequisite_not_fulfilled)
    def test_prerequisite_not_fulfilled(self, scenario_params, tested_object):
        """Test that prerequisite is not met when the SR-IOV operator subscription is missing."""
        RuleTestBase.test_prerequisite_not_fulfilled(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
