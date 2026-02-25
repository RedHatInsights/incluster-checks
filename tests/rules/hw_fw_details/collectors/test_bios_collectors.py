"""
Unit tests for BIOS/Firmware data collectors.

Tests BIOSVersion, BIOSFirmware, BIOSRevision, and BIOSReleaseDate collectors.
"""

import pytest
from unittest.mock import Mock

from openshift_in_cluster_checks.rules.hw_fw_details.collectors.bios_collectors import (
    BIOSFirmware,
    BIOSReleaseDate,
    BIOSRevision,
    BIOSVersion,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestBIOSVersion(DataCollectorTestBase):
    """Test BIOSVersion data collector."""

    tested_type = BIOSVersion

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="BIOS version from dmidecode",
            cmd_input_output_dict={"sudo dmidecode -s bios-version": CmdOutput(out="2.8.0\n")},
            scenario_res={"1": "2.8.0"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test BIOSVersion collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for BIOSVersion."""
        tested_object.get_component_ids = Mock(return_value=["1"])


class TestBIOSFirmware(DataCollectorTestBase):
    """Test BIOSFirmware data collector."""

    tested_type = BIOSFirmware

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="firmware revision with tab prefix",
            cmd_input_output_dict={"sudo dmidecode --type bios | grep 'Firmware Revision'": CmdOutput(out="\tFirmware Revision: 1.68\n")},
            scenario_res={"1": "1.68"},
        ),
        DataCollectorScenarioParams(
            scenario_title="firmware revision without tab",
            cmd_input_output_dict={"sudo dmidecode --type bios | grep 'Firmware Revision'": CmdOutput(out="Firmware Revision: 1.2\n")},
            scenario_res={"1": "1.2"},
        ),
        DataCollectorScenarioParams(
            scenario_title="firmware revision with empty output",
            cmd_input_output_dict={"sudo dmidecode --type bios | grep 'Firmware Revision'": CmdOutput(out="")},
            scenario_res={"1": ""},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test BIOSFirmware collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestBIOSRevision(DataCollectorTestBase):
    """Test BIOSRevision data collector."""

    tested_type = BIOSRevision

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="BIOS revision with tab prefix",
            cmd_input_output_dict={"sudo dmidecode --type bios | grep -i 'BIOS Revision'": CmdOutput(out="\tBIOS Revision: 5.12\n")},
            scenario_res={"1": "5.12"},
        ),
        DataCollectorScenarioParams(
            scenario_title="BIOS revision without tab",
            cmd_input_output_dict={"sudo dmidecode --type bios | grep -i 'BIOS Revision'": CmdOutput(out="BIOS Revision: 2.50\n")},
            scenario_res={"1": "2.50"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test BIOSRevision collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for BIOSRevision."""
        tested_object.get_component_ids = Mock(return_value=["1"])


class TestBIOSReleaseDate(DataCollectorTestBase):
    """Test BIOSReleaseDate data collector."""

    tested_type = BIOSReleaseDate

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="BIOS release date",
            cmd_input_output_dict={"sudo dmidecode -s bios-release-date": CmdOutput(out="12/15/2023\n")},
            scenario_res={"1": "12/15/2023"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test BIOSReleaseDate collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for BIOSReleaseDate."""
        tested_object.get_component_ids = Mock(return_value=["1"])
