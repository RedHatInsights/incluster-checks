"""
Unit tests for OS/Kernel data collectors.

Tests OperatingSystemVersion and KernelVersion collectors.
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.hw_fw_details.collectors.os_collectors import (
    KernelVersion,
    OperatingSystemVersion,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestOperatingSystemVersion(DataCollectorTestBase):
    """Test OperatingSystemVersion data collector."""

    tested_type = OperatingSystemVersion

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="RHEL 9.2",
            cmd_input_output_dict={"cat /etc/redhat-release": CmdOutput(out="Red Hat Enterprise Linux release 9.2 (Plow)\n")},
            scenario_res={"1": "Red Hat Enterprise Linux release 9.2 (Plow)"},
        ),
        DataCollectorScenarioParams(
            scenario_title="RHEL 8.6",
            cmd_input_output_dict={"cat /etc/redhat-release": CmdOutput(out="Red Hat Enterprise Linux release 8.6 (Ootpa)\n")},
            scenario_res={"1": "Red Hat Enterprise Linux release 8.6 (Ootpa)"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test OperatingSystemVersion collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for OperatingSystemVersion."""
        tested_object.get_component_ids = Mock(return_value=["1"])


class TestKernelVersion(DataCollectorTestBase):
    """Test KernelVersion data collector."""

    tested_type = KernelVersion

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="RHEL 9.2 kernel",
            cmd_input_output_dict={"uname -r": CmdOutput(out="5.14.0-284.11.1.el9_2.x86_64\n")},
            scenario_res={"1": "5.14.0-284.11.1.el9_2.x86_64"},
        ),
        DataCollectorScenarioParams(
            scenario_title="RHEL 8.6 kernel",
            cmd_input_output_dict={"uname -r": CmdOutput(out="4.18.0-372.9.1.el8.x86_64\n")},
            scenario_res={"1": "4.18.0-372.9.1.el8.x86_64"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test KernelVersion collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for KernelVersion."""
        tested_object.get_component_ids = Mock(return_value=["1"])
