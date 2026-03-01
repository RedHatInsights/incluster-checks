"""
Unit tests for Blueprint Firmware Rule.

Tests the Blueprint firmware validation rule including data collection,
uniformity checking, and result formatting.
"""

from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.rules.hw_fw_details.firmware_rule import FirmwareDetailsRule
from in_cluster_checks.rules.hw_fw_details.collectors.os_collectors import OperatingSystemVersion, KernelVersion
from in_cluster_checks.rules.hw_fw_details.collectors.bios_collectors import BIOSVersion
from in_cluster_checks.utils.enums import Status


class TestFirmwareDetailsRule:
    """Test FirmwareDetailsRule class."""

    def test_get_data_collectors(self):
        """Test that rule returns correct firmware data collectors."""
        rule = FirmwareDetailsRule()
        collectors = rule.get_data_collectors()

        # Verify OS/Kernel collectors
        assert OperatingSystemVersion in collectors
        assert KernelVersion in collectors
        # Verify BIOS collectors
        assert BIOSVersion in collectors
        # Should have 6 collectors total (OS, Kernel, 4 BIOS)
        assert len(collectors) == 6

    def test_get_data_category_key(self):
        """Test that rule returns correct data category key."""
        rule = FirmwareDetailsRule()
        assert rule.get_data_category_key() == "firmware"

    def test_unique_name(self):
        """Test rule unique name."""
        rule = FirmwareDetailsRule()
        assert rule.unique_name == "firmware_details"

    def test_title(self):
        """Test rule title."""
        rule = FirmwareDetailsRule()
        assert rule.title == "Firmware Details"

    @patch("in_cluster_checks.rules.hw_fw_details.hw_fw_base.HwFwRule._collect_all_data")
    @patch("in_cluster_checks.rules.hw_fw_details.hw_fw_base.HwFwRule.compare_within_groups")
    def test_run_rule_calls_base_methods(self, mock_compare, mock_collect):
        """Test that run_rule calls base class methods correctly."""
        rule = FirmwareDetailsRule()

        # Mock executor
        mock_executor = Mock()
        mock_executor.node_name = "master-0"
        mock_executor.node_labels = "master"

        # _node_executors should be a dict, not list
        rule._node_executors = {"master-0": mock_executor}

        # Mock return values
        mock_collect.return_value = {}
        mock_compare.return_value = Mock(status=Status.INFO)

        # Run the rule
        result = rule.run_rule()

        # Verify base methods were called
        assert mock_collect.called
        assert mock_compare.called
        assert result.status == Status.INFO

    @patch("in_cluster_checks.rules.hw_fw_details.hw_fw_base.HwFwRule._group_nodes_by_labels")
    @patch("in_cluster_checks.rules.hw_fw_details.hw_fw_base.HwFwRule._collect_all_data")
    def test_run_rule_groups_nodes(self, mock_collect, mock_group):
        """Test that run_rule groups nodes by labels."""
        rule = FirmwareDetailsRule()

        # Mock executors
        mock_executor1 = Mock()
        mock_executor1.node_name = "master-0"
        mock_executor2 = Mock()
        mock_executor2.node_name = "worker-0"

        rule._node_executors = [mock_executor1, mock_executor2]

        # Mock node groups
        mock_group.return_value = {
            "master": [mock_executor1],
            "worker": [mock_executor2]
        }
        mock_collect.return_value = {}

        # Run the rule
        rule.run_rule()

        # Verify grouping was called
        assert mock_group.called

    def test_check_group_uniformity_uniform_firmware(self):
        """Test uniformity check with uniform firmware data."""
        rule = FirmwareDetailsRule()

        # All nodes have identical firmware
        group_data = {
            "master-0": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
            "master-1": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
            "master-2": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
        }

        result = rule._check_group_uniformity(group_data)
        assert result is True

    def test_check_group_uniformity_mixed_firmware(self):
        """Test uniformity check with mixed firmware data."""
        rule = FirmwareDetailsRule()

        # Some nodes have different firmware
        group_data = {
            "worker-0": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
            "worker-1": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
            "worker-2": {"1": "Red Hat Enterprise Linux release 8.6 (Ootpa)"},
        }

        result = rule._check_group_uniformity(group_data)
        assert result is False

    def test_run_rule_hc_nested_format(self):
        """Test that run_rule returns HC-style nested format in blueprint_data."""
        # Mock executors
        mock_executor1 = Mock()
        mock_executor1.node_name = "master-0"
        mock_executor1.node_labels = "master"

        rule = FirmwareDetailsRule()
        rule._node_executors = {"master-0": mock_executor1}

        # Mock data returned by run_data_collector
        mock_data = {
            "master-0": {"1": "some_value"}
        }

        def mock_run_dc(*args, **kwargs):
            rule.any_passed_data_collector = True
            return mock_data

        with patch.object(rule, 'run_data_collector', side_effect=mock_run_dc):
            result = rule.run_rule()

        # Verify blueprint_data has HC nested structure
        assert "blueprint_data" in result.extra
        blueprint_data = result.extra["blueprint_data"]

        # Check master group exists
        assert "master" in blueprint_data

        master_data = blueprint_data["master"]
        assert "firmware" in master_data

        firmware_data = master_data["firmware"]

        # Verify OS/Kernel objectives
        assert "Operating System" in firmware_data
        assert "version" in firmware_data["Operating System"]

        assert "Kernel" in firmware_data
        assert "version" in firmware_data["Kernel"]

        # Verify BIOS objectives (note: topic is "Bios" not "BIOS")
        assert "Bios" in firmware_data
        assert "version" in firmware_data["Bios"]
        assert "firmware" in firmware_data["Bios"]
        assert "revision" in firmware_data["Bios"]
        assert "release-date" in firmware_data["Bios"]  # Hyphenated in output

        # Each objective should have is_uniform and value
        for topic in firmware_data.values():
            for objective_data in topic.values():
                assert "is_uniform" in objective_data
                assert "value" in objective_data

    def test_run_rule_with_non_uniform_firmware(self):
        """Test run_rule with non-uniform firmware shows correct uniformity status."""
        # Mock executors
        mock_executor1 = Mock()
        mock_executor1.node_name = "worker-0"
        mock_executor1.node_labels = "worker"

        mock_executor2 = Mock()
        mock_executor2.node_name = "worker-1"
        mock_executor2.node_labels = "worker"

        rule = FirmwareDetailsRule()
        rule._node_executors = {"worker-0": mock_executor1, "worker-1": mock_executor2}

        # Create different OS versions but same kernel
        os_data = {
            "worker-0": {"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
            "worker-1": {"1": "Red Hat Enterprise Linux release 8.6 (Ootpa)"}
        }

        kernel_data = {
            "worker-0": {"1": "5.14.0-284.11.1.el9_2.x86_64"},
            "worker-1": {"1": "5.14.0-284.11.1.el9_2.x86_64"}
        }

        # Mock run_data_collector to return different data per collector
        # Note: run_data_collector signature is (collector_class) only
        def mock_run_collector(collector_class):
            rule.any_passed_data_collector = True
            if collector_class.unique_name == "os_version":
                return os_data
            elif collector_class.unique_name == "kernel_version":
                return kernel_data
            else:
                # BIOS collectors - return same data
                return {
                    "worker-0": {"1": "same_value"},
                    "worker-1": {"1": "same_value"}
                }

        with patch.object(rule, 'run_data_collector', side_effect=mock_run_collector):
            result = rule.run_rule()

        # Verify result
        assert result.status == Status.INFO
        firmware_data = result.extra["blueprint_data"]["worker"]["firmware"]

        # OS version should be non-uniform (different OS versions)
        assert firmware_data["Operating System"]["version"]["is_uniform"] is False
        # Kernel should be uniform (same kernel version)
        assert firmware_data["Kernel"]["version"]["is_uniform"] is True
        # Bios should be uniform (note: topic is "Bios" not "BIOS")
        assert firmware_data["Bios"]["version"]["is_uniform"] is True
