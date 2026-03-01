"""
Unit tests for Memory data collectors.

Tests MemorySize, MemoryType, MemorySpeed, and MemoryTotalSize collectors.
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.hw_fw_details.collectors.memory_collectors import (
    MemorySize,
    MemorySpeed,
    MemoryTotalSize,
    MemoryType,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestMemorySize(DataCollectorTestBase):
    """Test MemorySize data collector."""

    tested_type = MemorySize

    # Sample dmidecode output with 4x 32GB memory modules
    dmidecode_output = """# dmidecode 3.3
Handle 0x001A, DMI type 17, 84 bytes
Memory Device
\tArray Handle: 0x0019
\tError Information Handle: Not Provided
\tTotal Width: 72 bits
\tData Width: 64 bits
\tSize: 32 GB
\tForm Factor: DIMM
\tSet: None
\tLocator: DIMM_A1
\tBank Locator: NODE 0
\tType: DDR4
\tType Detail: Synchronous Registered (Buffered)
\tSpeed: 3200 MT/s

Handle 0x001B, DMI type 17, 84 bytes
Memory Device
\tLocator: DIMM_A2
\tSize: 32 GB
\tType: DDR4
\tSpeed: 3200 MT/s

Handle 0x001C, DMI type 17, 84 bytes
Memory Device
\tLocator: DIMM_B1
\tSize: 32768 MB
\tType: DDR4
\tSpeed: 3200 MT/s

Handle 0x001D, DMI type 17, 84 bytes
Memory Device
\tLocator: DIMM_B2
\tSize: No Module Installed

Handle 0x001E, DMI type 17, 84 bytes
Memory Device
\tLocator: DIMM_C1
\tSize: 16 GB
\tType: DDR4
\tSpeed: 3200 MT/s"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="mixed memory sizes (GB and MB)",
            cmd_input_output_dict={"sudo dmidecode -t memory": CmdOutput(out=dmidecode_output)},
            scenario_res={
                "DIMM_A1": 32768,  # 32 GB = 32768 MB
                "DIMM_A2": 32768,  # 32 GB = 32768 MB
                "DIMM_B1": 32768,  # 32768 MB
                "DIMM_C1": 16384,  # 16 GB = 16384 MB
                # DIMM_B2 is "No Module Installed" so it's filtered out
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test MemorySize collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for MemorySize."""
        # Mock get_component_ids to return only populated slots
        tested_object.get_component_ids = Mock(return_value=["DIMM_A1", "DIMM_A2", "DIMM_B1", "DIMM_C1"])


class TestMemoryType(DataCollectorTestBase):
    """Test MemoryType data collector."""

    tested_type = MemoryType

    # Only include the DIMMs we want to test
    dmidecode_output = """Handle 0x001A, DMI type 17, 84 bytes
Memory Device
\tArray Handle: 0x0019
\tError Information Handle: Not Provided
\tTotal Width: 72 bits
\tData Width: 64 bits
\tSize: 32 GB
\tForm Factor: DIMM
\tSet: None
\tLocator: DIMM_A1
\tBank Locator: NODE 0
\tType: DDR4
\tType Detail: Synchronous Registered (Buffered)

Handle 0x001B, DMI type 17, 84 bytes
Memory Device
\tArray Handle: 0x0019
\tError Information Handle: Not Provided
\tTotal Width: 72 bits
\tData Width: 64 bits
\tSize: 32 GB
\tForm Factor: DIMM
\tSet: None
\tLocator: DIMM_A2
\tBank Locator: NODE 0
\tType: DDR4
\tType Detail: Synchronous Registered (Buffered)"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="DDR4 memory modules",
            cmd_input_output_dict={"sudo dmidecode -t memory": CmdOutput(out=dmidecode_output)},
            scenario_res={"DIMM_A1": "DDR4", "DIMM_A2": "DDR4"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test MemoryType collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for MemoryType."""
        tested_object.get_component_ids = Mock(return_value=["DIMM_A1", "DIMM_A2"])


class TestMemorySpeed(DataCollectorTestBase):
    """Test MemorySpeed data collector."""

    tested_type = MemorySpeed

    # Only include the DIMMs we want to test
    dmidecode_output = """Handle 0x001A, DMI type 17, 84 bytes
Memory Device
\tArray Handle: 0x0019
\tError Information Handle: Not Provided
\tTotal Width: 72 bits
\tData Width: 64 bits
\tSize: 32 GB
\tForm Factor: DIMM
\tSet: None
\tLocator: DIMM_A1
\tBank Locator: NODE 0
\tType: DDR4
\tType Detail: Synchronous Registered (Buffered)
\tSpeed: 3200 MT/s

Handle 0x001B, DMI type 17, 84 bytes
Memory Device
\tArray Handle: 0x0019
\tError Information Handle: Not Provided
\tTotal Width: 72 bits
\tData Width: 64 bits
\tSize: 32 GB
\tForm Factor: DIMM
\tSet: None
\tLocator: DIMM_A2
\tBank Locator: NODE 0
\tType: DDR4
\tType Detail: Synchronous Registered (Buffered)
\tSpeed: 2933 MHz"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="memory modules with MT/s and MHz speeds",
            cmd_input_output_dict={"sudo dmidecode -t memory": CmdOutput(out=dmidecode_output)},
            scenario_res={"DIMM_A1": 3200, "DIMM_A2": 2933},  # Both converted to MHz
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test MemorySpeed collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for MemorySpeed."""
        tested_object.get_component_ids = Mock(return_value=["DIMM_A1", "DIMM_A2"])


class TestMemoryTotalSize(DataCollectorTestBase):
    """Test MemoryTotalSize data collector."""

    tested_type = MemoryTotalSize

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="total of 128 GB (4x 32GB)",
            cmd_input_output_dict={},  # MemoryTotalSize uses MemorySize collector
            scenario_res={"Total of all units": 131072},  # 128 GB = 131072 MB
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test MemoryTotalSize collect_data()."""
        # Mock MemorySize collector to return fake data
        mock_memory_size_collector = Mock()
        mock_memory_size_collector.collect_data = Mock(
            return_value={
                "DIMM_A1": 32768,
                "DIMM_A2": 32768,
                "DIMM_B1": 32768,
                "DIMM_B2": 32768,
            }
        )

        # Patch MemorySize constructor to return our mock
        from unittest.mock import patch

        with patch(
            "in_cluster_checks.rules.hw_fw_details.collectors.memory_collectors.MemorySize",
            return_value=mock_memory_size_collector,
        ):
            DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for MemoryTotalSize."""
        tested_object.get_component_ids = Mock(return_value=["Total of all units"])
