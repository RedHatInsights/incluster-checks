"""
Unit tests for NUMA data collectors.

Tests NumaSizeMemory, NumaCpus, and NumaNICs collectors.
"""

import pytest
from unittest.mock import Mock

from in_cluster_checks.rules.hw_fw_details.collectors.numa_collectors import (
    NumaCpus,
    NumaNICs,
    NumaSizeMemory,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestNumaSizeMemory(DataCollectorTestBase):
    """Test NumaSizeMemory data collector."""

    tested_type = NumaSizeMemory

    # Sample lscpu output for NUMA node count
    lscpu_numa_nodes = """Architecture:            x86_64
CPU op-mode(s):          32-bit, 64-bit
Byte Order:              Little Endian
CPU(s):                  64
NUMA node(s):            2
NUMA node0 CPU(s):       0-15,32-47
NUMA node1 CPU(s):       16-31,48-63"""

    # Sample meminfo for node 0
    meminfo_node0 = """Node 0 MemTotal:       32948232 kB
Node 0 MemFree:        28123456 kB
Node 0 MemUsed:         4824776 kB"""

    # Sample meminfo for node 1
    meminfo_node1 = """Node 1 MemTotal:       32948232 kB
Node 1 MemFree:        25123456 kB
Node 1 MemUsed:         7824776 kB"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="two NUMA nodes with equal memory",
            cmd_input_output_dict={
                "lscpu | grep 'NUMA node(s):'": CmdOutput(out="NUMA node(s):            2"),
                "cat /sys/devices/system/node/node0/meminfo": CmdOutput(out=meminfo_node0),
                "cat /sys/devices/system/node/node1/meminfo": CmdOutput(out=meminfo_node1),
            },
            scenario_res={
                "node 0": 32176,  # 32948232 kB / 1024 = 32176 MB
                "node 1": 32176,
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NumaSizeMemory collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNumaCpus(DataCollectorTestBase):
    """Test NumaCpus data collector."""

    tested_type = NumaCpus

    # Sample lscpu output with NUMA configuration
    lscpu_output = """Architecture:            x86_64
CPU op-mode(s):          32-bit, 64-bit
Byte Order:              Little Endian
Address sizes:           46 bits physical, 48 bits virtual
CPU(s):                  64
On-line CPU(s) list:     0-63
Thread(s) per core:      2
Core(s) per socket:      16
Socket(s):               2
NUMA node(s):            2
Vendor ID:               GenuineIntel
CPU family:              6
Model:                   85
Model name:              Intel(R) Xeon(R) Gold 6238 CPU @ 2.10GHz
Stepping:                7
CPU MHz:                 2100.000
BogoMIPS:                4200.00
Virtualization:          VT-x
L1d cache:               1 MiB
L1i cache:               1 MiB
L2 cache:                32 MiB
L3 cache:                30.25 MiB
NUMA node0 CPU(s):       0-15,32-47
NUMA node1 CPU(s):       16-31,48-63"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="two NUMA nodes with hyperthreading",
            cmd_input_output_dict={
                "lscpu | grep 'NUMA node(s):'": CmdOutput(out="NUMA node(s):            2"),
                "lscpu": CmdOutput(out=lscpu_output),
            },
            scenario_res={
                "node 0": "0-15,32-47",
                "node 1": "16-31,48-63",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NumaCpus collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNumaNICs(DataCollectorTestBase):
    """Test NumaNICs data collector."""

    tested_type = NumaNICs

    # Sample lscpu for NUMA node count
    lscpu_numa_nodes = "NUMA node(s):            2"

    # Sample ls output for physical NICs (with 'np' suffix)
    ls_net_output = """ens1f0np0
ens1f1np1
ens2f0np0
ens2f1np1"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="four physical NICs split across two NUMA nodes",
            cmd_input_output_dict={
                "lscpu | grep 'NUMA node(s):'": CmdOutput(out=lscpu_numa_nodes),
                "ls /sys/class/net/ | grep np": CmdOutput(out=ls_net_output),
                # NUMA node affinity
                "cat /sys/class/net/ens1f0np0/device/numa_node": CmdOutput(out="0"),
                "cat /sys/class/net/ens1f1np1/device/numa_node": CmdOutput(out="0"),
                "cat /sys/class/net/ens2f0np0/device/numa_node": CmdOutput(out="1"),
                "cat /sys/class/net/ens2f1np1/device/numa_node": CmdOutput(out="1"),
            },
            scenario_res={
                "node 0": ["ens1f0np0", "ens1f1np1"],
                "node 1": ["ens2f0np0", "ens2f1np1"],
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NumaNICs collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)
