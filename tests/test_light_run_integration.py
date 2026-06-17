"""Integration tests for --light-run flag."""

import pytest

from in_cluster_checks import global_config
from in_cluster_checks.domains.hw_fw_details_domain import HwFwDetailsValidationDomain
from in_cluster_checks.domains.k8s_domain import K8sValidationDomain
from in_cluster_checks.rules.hw_fw_details.firmware_rule import FirmwareDetailsRule
from in_cluster_checks.rules.hw_fw_details.hardware_rule import HardwareDetailsRule


@pytest.fixture(autouse=True)
def reset_light_run():
    """Reset light_run flag after each test."""
    yield
    global_config.light_run = False


class TestLightRunIntegration:
    """Integration tests for light-run mode."""

    def test_normal_mode_includes_hw_fw_details_rules(self):
        """Normal mode should include hw_fw_details rules."""
        global_config.light_run = False

        domain = HwFwDetailsValidationDomain()
        all_rules = domain.get_rule_classes()
        filtered_rules = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered_rules) == 2
        assert HardwareDetailsRule in filtered_rules
        assert FirmwareDetailsRule in filtered_rules

    def test_light_mode_excludes_hw_fw_details_rules(self):
        """Light mode should exclude hw_fw_details rules."""
        global_config.light_run = True

        domain = HwFwDetailsValidationDomain()
        all_rules = domain.get_rule_classes()
        filtered_rules = domain._filter_rules_for_light_run(all_rules)

        assert len(filtered_rules) == 0

    def test_light_mode_includes_k8s_rules(self):
        """Light mode should still include K8s rules (they have include_in_light_run=True)."""
        global_config.light_run = True

        domain = K8sValidationDomain()
        all_rules = domain.get_rule_classes()
        filtered_rules = domain._filter_rules_for_light_run(all_rules)

        # K8s rules should all be included (default include_in_light_run=True)
        assert len(filtered_rules) > 0

    def test_hw_fw_details_rules_have_include_in_light_run_false(self):
        """Verify hw_fw_details rules have include_in_light_run=False."""
        assert HardwareDetailsRule.include_in_light_run is False
        assert FirmwareDetailsRule.include_in_light_run is False
