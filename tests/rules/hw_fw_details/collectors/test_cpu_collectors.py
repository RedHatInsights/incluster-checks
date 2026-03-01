"""
Unit tests for CPU data collectors.

Tests ProcessorType, ProcessorCurrentFrequency, and NumberOfThreadsPerCore collectors.
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.hw_fw_details.collectors.cpu_collectors import (
    NumberOfPhysicalCoresPerProcessor,
    NumberOfThreadsPerCore,
    ProcessorCurrentFrequency,
    ProcessorType,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestProcessorType(DataCollectorTestBase):
    """Test ProcessorType data collector."""

    tested_type = ProcessorType

    # Sample dmidecode output
    dmidecode_output = """# dmidecode 3.3
Getting SMBIOS data from sysfs.
SMBIOS 3.2.0 present.

Handle 0x0004, DMI type 4, 48 bytes
Processor Information
\tSocket Designation: CPU0
\tType: Central Processor
\tFamily: Xeon
\tManufacturer: Intel(R) Corporation
\tVersion: Intel(R) Xeon(R) Gold 6238 CPU @ 2.10GHz

Handle 0x0005, DMI type 4, 48 bytes
Processor Information
\tSocket Designation: CPU1
\tType: Central Processor
\tFamily: Xeon
\tManufacturer: Intel(R) Corporation
\tVersion: Intel(R) Xeon(R) Gold 6238 CPU @ 2.10GHz"""

    # Sample lscpu output
    lscpu_output = """Architecture:        x86_64
CPU op-mode(s):      32-bit, 64-bit
Byte Order:          Little Endian
CPU(s):              88
On-line CPU(s) list: 0-87
Thread(s) per core:  2
Core(s) per socket:  22
Socket(s):           2
NUMA node(s):        2
Vendor ID:           GenuineIntel
CPU family:          6
Model:               85
Model name:          Intel(R) Xeon(R) Gold 6238 CPU @ 2.10GHz
Stepping:            7
CPU MHz:             2100.000"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="two processor sockets with same CPU model",
            cmd_input_output_dict={
                "sudo dmidecode -t processor": CmdOutput(out=dmidecode_output),
                "lscpu": CmdOutput(out=lscpu_output),
            },
            scenario_res={"CPU0": "Intel Xeon Gold 6238 CPU", "CPU1": "Intel Xeon Gold 6238 CPU"},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test ProcessorType collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for ProcessorType."""
        # Mock get_component_ids to return socket designations from dmidecode
        tested_object.get_component_ids = Mock(return_value=["CPU0", "CPU1"])


class TestProcessorCurrentFrequency(DataCollectorTestBase):
    """Test ProcessorCurrentFrequency data collector."""

    tested_type = ProcessorCurrentFrequency

    # Need full dmidecode output with "Processor Information" header
    dmidecode_output = """# dmidecode 3.3
Handle 0x0004, DMI type 4, 48 bytes
Processor Information
\tSocket Designation: CPU0
\tType: Central Processor
\tCurrent Speed: 2100 MHz

Handle 0x0005, DMI type 4, 48 bytes
Processor Information
\tSocket Designation: CPU1
\tType: Central Processor
\tCurrent Speed: 2100 MHz"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="two processors at 2100 MHz",
            cmd_input_output_dict={"sudo dmidecode -t processor": CmdOutput(out=dmidecode_output)},
            scenario_res={"CPU0": 2100, "CPU1": 2100},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test ProcessorCurrentFrequency collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for ProcessorCurrentFrequency."""
        tested_object.get_component_ids = Mock(return_value=["CPU0", "CPU1"])


class TestNumberOfThreadsPerCore(DataCollectorTestBase):
    """Test NumberOfThreadsPerCore data collector."""

    tested_type = NumberOfThreadsPerCore

    lscpu_output = """Architecture:        x86_64
Thread(s) per core:  2
Core(s) per socket:  22
Socket(s):           2"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="2 threads per core",
            cmd_input_output_dict={"lscpu": CmdOutput(out=lscpu_output)},
            scenario_res={"CPU0": 2, "CPU1": 2},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NumberOfThreadsPerCore collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for NumberOfThreadsPerCore."""
        tested_object.get_component_ids = Mock(return_value=["CPU0", "CPU1"])


class TestNumberOfPhysicalCoresPerProcessor(DataCollectorTestBase):
    """Test NumberOfPhysicalCoresPerProcessor data collector."""

    tested_type = NumberOfPhysicalCoresPerProcessor

    lscpu_output = """Architecture:        x86_64
Thread(s) per core:  2
Core(s) per socket:  22
Socket(s):           2"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="22 physical cores per processor socket",
            cmd_input_output_dict={"lscpu": CmdOutput(out=lscpu_output)},
            scenario_res={"CPU0": 22, "CPU1": 22},
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NumberOfPhysicalCoresPerProcessor collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)

    def _init_mocks(self, tested_object, scenario_params):
        """Additional mocks for NumberOfPhysicalCoresPerProcessor."""
        tested_object.get_component_ids = Mock(return_value=["CPU0", "CPU1"])
