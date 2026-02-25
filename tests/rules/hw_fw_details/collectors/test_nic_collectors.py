"""
Unit tests for NIC data collectors.

Tests NICVendor, NICModel, and NICSpeed collectors.
"""

import pytest
from unittest.mock import Mock

from openshift_in_cluster_checks.rules.hw_fw_details.collectors.nic_collectors import (
    NICDriver,
    NICFirmware,
    NICModel,
    NICPortsAmount,
    NICPortsNames,
    NICSpeed,
    NICVendor,
    NICVersion,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestNICVendor(DataCollectorTestBase):
    """Test NICVendor data collector."""

    tested_type = NICVendor

    # Sample lspci output
    lspci_output = """00:1f.6 Ethernet controller [0200]: Intel Corporation Ethernet Connection (7) I219-LM [8086:15bb] (rev 10)
01:00.0 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)
01:00.1 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)"""

    # Sample lspci -vmm output for individual NICs
    lspci_vmm_001f6 = """Slot:\t00:1f.6
Class:\tEthernet controller
Vendor:\tIntel Corporation
Device:\tEthernet Connection (7) I219-LM"""

    lspci_vmm_01000 = """Slot:\t01:00.0
Class:\tEthernet controller
Vendor:\tIntel Corporation
Device:\tEthernet Controller X710 for 10GbE SFP+"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="three NICs with Intel controllers",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "sudo lspci -vmm -s 00:1f.6": CmdOutput(out=lspci_vmm_001f6),
                "sudo lspci -vmm -s 01:00.0": CmdOutput(out=lspci_vmm_01000),
            },
            scenario_res={
                "00:1f": "Intel Corporation",
                "01:00": "Intel Corporation",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICVendor collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICModel(DataCollectorTestBase):
    """Test NICModel data collector."""

    tested_type = NICModel

    lspci_output = """00:1f.6 Ethernet controller [0200]: Intel Corporation Ethernet Connection (7) I219-LM [8086:15bb] (rev 10)
01:00.0 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)
01:00.1 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)"""

    lspci_vmm_001f6 = """Slot:\t00:1f.6
Class:\tEthernet controller
Vendor:\tIntel Corporation
Device:\tEthernet Connection (7) I219-LM"""

    lspci_vmm_01000 = """Slot:\t01:00.0
Class:\tEthernet controller
Vendor:\tIntel Corporation
Device:\tEthernet Controller X710 for 10GbE SFP+"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NICs with different models",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "sudo lspci -vmm -s 00:1f.6": CmdOutput(out=lspci_vmm_001f6),
                "sudo lspci -vmm -s 01:00.0": CmdOutput(out=lspci_vmm_01000),
            },
            scenario_res={
                "00:1f": "Ethernet Connection (7) I219-LM",
                "01:00": "Ethernet Controller X710 for 10GbE SFP+",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICModel collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICSpeed(DataCollectorTestBase):
    """Test NICSpeed data collector."""

    tested_type = NICSpeed

    # Sample ethtool outputs for different NICs
    ethtool_eno1 = """Settings for eno1:
\tSupported ports: [ TP ]
\tSupported link modes:   10baseT/Half 10baseT/Full
\t                        100baseT/Half 100baseT/Full
\t                        1000baseT/Full
\tSupported pause frame use: No
\tSupports auto-negotiation: Yes
\tSupported FEC modes: Not reported
\tAdvertised link modes:  10baseT/Half 10baseT/Full
\t                        100baseT/Half 100baseT/Full
\t                        1000baseT/Full
\tAdvertised pause frame use: No
\tAdvertised auto-negotiation: Yes
\tAdvertised FEC modes: Not reported
\tSpeed: 1000Mb/s
\tDuplex: Full
\tAuto-negotiation: on
\tPort: Twisted Pair"""

    ethtool_ens1f0 = """Settings for ens1f0:
\tSupported ports: [ FIBRE ]
\tSupported link modes:   10000baseT/Full
\tSupported pause frame use: Symmetric
\tSupports auto-negotiation: No
\tSupported FEC modes: Not reported
\tAdvertised link modes:  10000baseT/Full
\tAdvertised pause frame use: Symmetric
\tAdvertised auto-negotiation: No
\tAdvertised FEC modes: Not reported
\tSpeed: 10000Mb/s
\tDuplex: Full
\tAuto-negotiation: off
\tPort: FIBRE"""

    ethtool_ens1f1 = """Settings for ens1f1:
\tSupported ports: [ FIBRE ]
\tSupported link modes:   10000baseT/Full
\tSupported pause frame use: Symmetric
\tSupports auto-negotiation: No
\tSupported FEC modes: Not reported
\tAdvertised link modes:  10000baseT/Full
\tAdvertised pause frame use: Symmetric
\tAdvertised auto-negotiation: No
\tAdvertised FEC modes: Not reported
\tSpeed: Unknown!
\tDuplex: Unknown! (255)
\tAuto-negotiation: off
\tPort: FIBRE
\tLink detected: no"""

    lspci_output = """00:1f.6 Ethernet controller [0200]: Intel Corporation Ethernet Connection (7) I219-LM [8086:15bb] (rev 10)
01:00.0 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)
01:00.1 Ethernet controller [0200]: Intel Corporation Ethernet Controller X710 for 10GbE SFP+ [8086:1572] (rev 02)"""

    sysfs_physical_interfaces = """eno1
ens1f0
ens1f1"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NICs with different speeds",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(out=sysfs_physical_interfaces),
                "readlink /sys/class/net/eno1/device 2>/dev/null": CmdOutput(out="../../../0000:00:1f.6"),
                "readlink /sys/class/net/ens1f0/device 2>/dev/null": CmdOutput(out="../../../0000:01:00.0"),
                "readlink /sys/class/net/ens1f1/device 2>/dev/null": CmdOutput(out="../../../0000:01:00.1"),
                "sudo ethtool eno1": CmdOutput(out=ethtool_eno1),
                "sudo ethtool ens1f0": CmdOutput(out=ethtool_ens1f0),
            },
            scenario_res={
                "00:1f": 1000,
                "01:00": 10000,
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICSpeed collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICPortsAmount(DataCollectorTestBase):
    """Test NICPortsAmount data collector."""

    tested_type = NICPortsAmount

    lspci_output = """12:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
12:00.1 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
9f:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
9f:00.1 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
b4:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="three NICs with different port counts",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
            },
            scenario_res={
                "12:00": 2,  # Two ports: .0 and .1
                "9f:00": 2,  # Two ports: .0 and .1
                "b4:00": 1,  # One port: .0
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICPortsAmount collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICPortsNames(DataCollectorTestBase):
    """Test NICPortsNames data collector."""

    tested_type = NICPortsNames

    lspci_output = """0000:12:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
0000:12:00.1 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
0000:9f:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""

    # Mock physical interfaces list (output from ls -d /sys/class/net/*/device)
    sysfs_physical_interfaces = """ens1f0np0
ens1f1np1
ens3f0np0"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NICs with logical port names",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                # Mock ls -d /sys/class/net/*/device to get physical interfaces only
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(out=sysfs_physical_interfaces),
                # Mock PCI address lookups via readlink
                "readlink /sys/class/net/ens1f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.0"),
                "readlink /sys/class/net/ens1f1np1/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.1"),
                "readlink /sys/class/net/ens3f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:9f:00.0"),
            },
            scenario_res={
                "0000:12:00": "ens1f0np0 ens1f1np1",
                "0000:9f:00": "ens3f0np0",
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="NICs with non-0000 PCI domain (SR-IOV scenario)",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(
                    out="""0000:10:00.0 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0000:10:00.1 Ethernet controller: Mellanox Technologies MT2910 Family [ConnectX-7]
0001:10:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
0001:10:00.1 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""
                ),
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(
                    out="""ens2f0np0
ens2f1np1
enP1s4f0np0
enP1s4f1np1"""
                ),
                # Domain 0000 NICs
                "readlink /sys/class/net/ens2f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:10:00.0"),
                "readlink /sys/class/net/ens2f1np1/device 2>/dev/null": CmdOutput(out="../../../0000:10:00.1"),
                # Domain 0001 NICs (SR-IOV physical functions)
                "readlink /sys/class/net/enP1s4f0np0/device 2>/dev/null": CmdOutput(out="../../../0001:10:00.0"),
                "readlink /sys/class/net/enP1s4f1np1/device 2>/dev/null": CmdOutput(out="../../../0001:10:00.1"),
            },
            scenario_res={
                "0000:10:00": "ens2f0np0 ens2f1np1",
                "0001:10:00": "enP1s4f0np0 enP1s4f1np1",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICPortsNames collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICVersion(DataCollectorTestBase):
    """Test NICVersion data collector."""

    tested_type = NICVersion

    lspci_output = """0000:12:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]
0000:12:00.1 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""

    sysfs_physical_interfaces = """ens1f0np0
ens1f1np1"""

    ethtool_i_output = """driver: mlx5_core
version: 5.14.0-570.83.1.el9_6.x86_64
firmware-version: 26.44.1036 (MT_0000000575)
expansion-rom-version:
bus-info: 0000:12:00.0
supports-statistics: yes"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NIC with driver version",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(out=sysfs_physical_interfaces),
                "readlink /sys/class/net/ens1f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.0"),
                "readlink /sys/class/net/ens1f1np1/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.1"),
                "sudo ethtool -i ens1f0np0": CmdOutput(out=ethtool_i_output),
            },
            scenario_res={
                "0000:12:00": "5.14.0-570.83.1.el9_6.x86_64",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICVersion collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICFirmware(DataCollectorTestBase):
    """Test NICFirmware data collector."""

    tested_type = NICFirmware

    lspci_output = """12:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""

    sysfs_physical_interfaces = """ens1f0np0"""

    ethtool_i_output = """driver: mlx5_core
version: 5.14.0-570.83.1.el9_6.x86_64
firmware-version: 26.44.1036 (MT_0000000575)
expansion-rom-version:
bus-info: 0000:12:00.0"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NIC with firmware version",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(out=sysfs_physical_interfaces),
                "readlink /sys/class/net/ens1f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.0"),
                "sudo ethtool -i ens1f0np0": CmdOutput(out=ethtool_i_output),
            },
            scenario_res={
                "12:00": "26.44.1036 (MT_0000000575)",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICFirmware collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestNICDriver(DataCollectorTestBase):
    """Test NICDriver data collector."""

    tested_type = NICDriver

    lspci_output = """12:00.0 Ethernet controller: Mellanox Technologies MT2894 Family [ConnectX-6 Lx]"""

    sysfs_physical_interfaces = """ens1f0np0"""

    ethtool_i_output = """driver: mlx5_core
version: 5.14.0-570.83.1.el9_6.x86_64
firmware-version: 26.44.1036 (MT_0000000575)
bus-info: 0000:12:00.0"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="NIC with driver name",
            cmd_input_output_dict={
                "sudo lspci | grep -i 'ethernet\\|infiniband' | grep -vi 'virtual'": CmdOutput(out=lspci_output),
                "ls -d /sys/class/net/*/device 2>/dev/null | cut -d'/' -f5": CmdOutput(out=sysfs_physical_interfaces),
                "readlink /sys/class/net/ens1f0np0/device 2>/dev/null": CmdOutput(out="../../../0000:12:00.0"),
                "sudo ethtool -i ens1f0np0": CmdOutput(out=ethtool_i_output),
            },
            scenario_res={
                "12:00": "mlx5_core",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test NICDriver collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)
