"""
Unit tests for Disk data collectors.

Tests DiskType, DiskModel, DiskVendor, and DiskSize collectors.
"""

import pytest

from openshift_in_cluster_checks.rules.hw_fw_details.collectors.disk_collectors import (
    DiskModel,
    DiskSize,
    DiskType,
    DiskVendor,
    OperatingSystemDiskName,
    OperatingSystemDiskSize,
    OperatingSystemDiskType,
)
from tests.pytest_tools.test_data_collector_base import (
    DataCollectorScenarioParams,
    DataCollectorTestBase,
)
from tests.pytest_tools.test_operator_base import CmdOutput


class TestDiskType(DataCollectorTestBase):
    """Test DiskType data collector."""

    tested_type = DiskType

    # Sample lsblk output
    lsblk_output = """NAME   MODEL                 ROTA
sda    SAMSUNG MZ7LH960         0
sdb    HGST HUH721010AL         1
nvme0n1 INTEL SSDPE2KX040T8    0"""

    # Sample smartctl output for SSD
    smartctl_sda = """smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.14.0-162.6.1.el9_1.x86_64] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

=== START OF INFORMATION SECTION ===
Model Family:     Samsung based SSDs
Device Model:     SAMSUNG MZ7LH960HAJR-00005
Serial Number:    S45PNA0M123456
LU WWN Device Id: 5 002538 e0a123456
Firmware Version: HXT7404Q
User Capacity:    960,197,124,096 bytes [960 GB]
Sector Size:      512 bytes logical/physical
Rotation Rate:    Solid State Device"""

    # Sample smartctl output for NVMe
    smartctl_nvme = """smartctl 7.2 2020-12-30 r5155 [x86_64-linux-5.14.0-162.6.1.el9_1.x86_64] (local build)
Copyright (C) 2002-20, Bruce Allen, Christian Franke, www.smartmontools.org

=== START OF INFORMATION SECTION ===
Model Number:                       INTEL SSDPE2KX040T8
Serial Number:                      PHLN123456789ABC
Firmware Version:                   VDV10170
PCI Vendor/Subsystem ID:            0x8086
IEEE OUI Identifier:                0x5cd2e4
Total NVM Capacity:                 4,000,797,999,104 [4.00 TB]
Unallocated NVM Capacity:           0
Controller ID:                      0"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="mixed disk types (SSD, HDD, NVMe)",
            cmd_input_output_dict={
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_output),
                "sudo lsblk -d -o name,rota": CmdOutput(
                    out="""NAME   ROTA
sda       0
sdb       1
nvme0n1   0"""
                ),
                "sudo smartctl -a /dev/sda": CmdOutput(out=smartctl_sda),
                "sudo smartctl -a /dev/nvme0n1": CmdOutput(out=smartctl_nvme),
            },
            scenario_res={
                "sda": "SSD",
                "sdb": "HDD",
                "nvme0n1": "NVMe",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test DiskType collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestDiskModel(DataCollectorTestBase):
    """Test DiskModel data collector."""

    tested_type = DiskModel

    lsblk_output = """NAME   MODEL
sda    SAMSUNG MZ7LH960
sdb    HGST HUH721010AL
nvme0n1 INTEL SSDPE2KX040T8"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="disks with different models",
            cmd_input_output_dict={
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_output),
            },
            scenario_res={
                "sda": "SAMSUNG MZ7LH960",
                "sdb": "HGST HUH721010AL",
                "nvme0n1": "INTEL SSDPE2KX040T8",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test DiskModel collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestDiskVendor(DataCollectorTestBase):
    """Test DiskVendor data collector."""

    tested_type = DiskVendor

    lsblk_vendor = """NAME   VENDOR
sda    SAMSUNG
sdb    HGST
nvme0n1 """

    lsblk_model = """NAME   MODEL
sda    SAMSUNG MZ7LH960
sdb    HGST HUH721010AL
nvme0n1 INTEL SSDPE2KX040T8"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="disks with vendor info (fallback to model for NVMe)",
            cmd_input_output_dict={
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_model),
                "sudo lsblk -d -o name,vendor": CmdOutput(out=lsblk_vendor),
            },
            scenario_res={
                "sda": "SAMSUNG",
                "sdb": "HGST",
                "nvme0n1": "INTEL SSDPE2KX040T8",  # Falls back to model
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test DiskVendor collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestDiskSize(DataCollectorTestBase):
    """Test DiskSize data collector."""

    tested_type = DiskSize

    lsblk_output = """NAME   SIZE
sda    960197124096
sdb    10000831348736
nvme0n1 4000797999104"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="disks with different sizes",
            cmd_input_output_dict={
                "sudo lsblk -d -o name,model": CmdOutput(
                    out="""NAME   MODEL
sda    SAMSUNG MZ7LH960
sdb    HGST HUH721010AL
nvme0n1 INTEL SSDPE2KX040T8"""
                ),
                "sudo lsblk -d -o name,size -b": CmdOutput(out=lsblk_output),
            },
            scenario_res={
                "sda": 915715,  # 960197124096 / 1048576 = 915715
                "sdb": 9537536,  # 10000831348736 / 1048576 = 9537536
                "nvme0n1": 3815458,  # 4000797999104 / 1048576 = 3815458
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test DiskSize collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestOperatingSystemDiskName(DataCollectorTestBase):
    """Test OperatingSystemDiskName data collector."""

    tested_type = OperatingSystemDiskName

    # Sample lsblk -n output with single disk
    lsblk_single_disk = """sda                                                             disk
├─sda1                                                          part /boot/efi
├─sda2                                                          part /boot
└─sda3                                                          part /
sdb                                                             disk
└─sdb1                                                          part /data"""

    # Sample lsblk -n output with LVM
    lsblk_lvm = """sda                                                             disk
├─sda1                                                          part /boot
└─sda2                                                          part
  └─vg0-root                                                    lvm  /
sdb                                                             disk"""

    # Sample lsblk -n output with RAID
    lsblk_raid = """sda                                                             disk
├─sda1                                                          part
└─md0                                                           raid /
sdb                                                             disk
└─sdb1                                                          part"""

    # Sample lsblk -n output from RHCOS with /sysroot mount
    lsblk_rhcos = """loop0    7:0    0   5.8M  1 loop
sda      8:0    0   3.5T  0 disk
sdb      8:16   0 894.3G  0 disk
|-sdb1   8:17   0     1M  0 part
|-sdb2   8:18   0   127M  0 part
|-sdb3   8:19   0   384M  0 part /boot
`-sdb4   8:20   0 893.8G  0 part /var/lib/kubelet/pods/ef6b93a7-528f-4015-bba1-daf9b8f39de5/volume-subpaths/nginx-conf/networking-console-plugin/1
                                 /var/opt/pwx/oci
                                 /var
                                 /sysroot/ostree/deploy/rhcos/var
                                 /sysroot
                                 /etc
sdc      8:32   0 894.3G  0 disk
`-sdc1   8:33   0 894.3G  0 part /var/lib/containers"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="single disk OS (sda with / mount)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_single_disk),
            },
            scenario_res={
                "operating_system_disk": "sda",
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="LVM root filesystem",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_lvm),
            },
            scenario_res={
                "operating_system_disk": "sda",
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="RAID root filesystem",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_raid),
            },
            scenario_res={
                "operating_system_disk": "sda",
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="RHCOS with /sysroot mount (sdb)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_rhcos),
            },
            scenario_res={
                "operating_system_disk": "sdb",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test OperatingSystemDiskName collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestOperatingSystemDiskType(DataCollectorTestBase):
    """Test OperatingSystemDiskType data collector."""

    tested_type = OperatingSystemDiskType

    def _init_data_collector_object(self, collector_object, scenario_params=None):
        """Initialize and pre-populate cache for nested collectors."""
        super()._init_data_collector_object(collector_object, scenario_params)

        # Pre-populate the class-level cache so nested collectors can use it
        # This is needed because OperatingSystemDiskType creates instances of
        # OperatingSystemDiskName and DiskType internally
        node_name = "test_node"
        if scenario_params:
            for cmd, cmd_output in scenario_params.cmd_input_output_dict.items():
                cache_key = (node_name, cmd)
                collector_object.cached_command_outputs[cache_key] = cmd_output.out

    # lsblk outputs
    lsblk_output = """sda                                                             disk
├─sda1                                                          part /boot/efi
└─sda2                                                          part /
sdb                                                             disk"""

    lsblk_disk_list = """NAME   MODEL
sda    SAMSUNG MZ7LH960
sdb    HGST HUH721010AL"""

    lsblk_rota = """NAME   ROTA
sda       0
sdb       1"""

    smartctl_sda = """smartctl 7.2 2020-12-30 r5155
Model Family:     Samsung based SSDs
Device Model:     SAMSUNG MZ7LH960HAJR-00005
Rotation Rate:    Solid State Device"""

    # RHCOS lsblk output with /sysroot mount
    lsblk_rhcos = """loop0    7:0    0   5.8M  1 loop
sda      8:0    0   3.5T  0 disk
sdb      8:16   0 894.3G  0 disk
|-sdb1   8:17   0     1M  0 part
|-sdb2   8:18   0   127M  0 part
|-sdb3   8:19   0   384M  0 part /boot
`-sdb4   8:20   0 893.8G  0 part /sysroot
sdc      8:32   0 894.3G  0 disk"""

    lsblk_disk_list_rhcos = """NAME   MODEL
sda    HGST HUH721010AL
sdb    SAMSUNG MZ7LH960
sdc    HGST HUH721010AL"""

    lsblk_rota_rhcos = """NAME   ROTA
sda       1
sdb       0
sdc       1"""

    smartctl_sdb = """smartctl 7.2 2020-12-30 r5155
Model Family:     Samsung based SSDs
Device Model:     SAMSUNG MZ7LH960HAJR-00005
Rotation Rate:    Solid State Device"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="OS disk is SSD (sda)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_output),
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_disk_list),
                "sudo lsblk -d -o name,rota": CmdOutput(out=lsblk_rota),
                "sudo smartctl -a /dev/sda": CmdOutput(out=smartctl_sda),
            },
            scenario_res={
                "operating_system_disk": "SSD",
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="RHCOS OS disk is SSD (sdb with /sysroot)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_rhcos),
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_disk_list_rhcos),
                "sudo lsblk -d -o name,rota": CmdOutput(out=lsblk_rota_rhcos),
                "sudo smartctl -a /dev/sdb": CmdOutput(out=smartctl_sdb),
            },
            scenario_res={
                "operating_system_disk": "SSD",
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test OperatingSystemDiskType collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)


class TestOperatingSystemDiskSize(DataCollectorTestBase):
    """Test OperatingSystemDiskSize data collector."""

    tested_type = OperatingSystemDiskSize

    def _init_data_collector_object(self, collector_object, scenario_params=None):
        """Initialize and pre-populate cache for nested collectors."""
        super()._init_data_collector_object(collector_object, scenario_params)

        # Pre-populate the class-level cache so nested collectors can use it
        # This is needed because OperatingSystemDiskSize creates instances of
        # OperatingSystemDiskName and DiskSize internally
        node_name = "test_node"
        if scenario_params:
            for cmd, cmd_output in scenario_params.cmd_input_output_dict.items():
                cache_key = (node_name, cmd)
                collector_object.cached_command_outputs[cache_key] = cmd_output.out

    # lsblk outputs
    lsblk_output = """sda                                                             disk
├─sda1                                                          part /boot/efi
└─sda2                                                          part /
sdb                                                             disk"""

    lsblk_disk_list = """NAME   MODEL
sda    SAMSUNG MZ7LH960
sdb    HGST HUH721010AL"""

    lsblk_size = """NAME   SIZE
sda    960197124096
sdb    10000831348736"""

    # RHCOS lsblk output with /sysroot mount
    lsblk_rhcos = """loop0    7:0    0   5.8M  1 loop
sda      8:0    0   3.5T  0 disk
sdb      8:16   0 894.3G  0 disk
|-sdb1   8:17   0     1M  0 part
|-sdb2   8:18   0   127M  0 part
|-sdb3   8:19   0   384M  0 part /boot
`-sdb4   8:20   0 893.8G  0 part /sysroot
sdc      8:32   0 894.3G  0 disk"""

    lsblk_disk_list_rhcos = """NAME   MODEL
sda    HGST HUH721010AL
sdb    SAMSUNG MZ7LH960
sdc    HGST HUH721010AL"""

    lsblk_size_rhcos = """NAME   SIZE
sda    3841082408960
sdb    960197124096
sdc    960197124096"""

    scenarios = [
        DataCollectorScenarioParams(
            scenario_title="OS disk size in MB (sda = 960197124096 bytes = 915715 MB)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_output),
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_disk_list),
                "sudo lsblk -d -o name,size -b": CmdOutput(out=lsblk_size),
            },
            scenario_res={
                "operating_system_disk": "915715",  # 960197124096 / 1048576
            },
        ),
        DataCollectorScenarioParams(
            scenario_title="RHCOS OS disk size in MB (sdb with /sysroot = 960197124096 bytes = 915715 MB)",
            cmd_input_output_dict={
                "sudo lsblk -n": CmdOutput(out=lsblk_rhcos),
                "sudo lsblk -d -o name,model": CmdOutput(out=lsblk_disk_list_rhcos),
                "sudo lsblk -d -o name,size -b": CmdOutput(out=lsblk_size_rhcos),
            },
            scenario_res={
                "operating_system_disk": "915715",  # 960197124096 / 1048576
            },
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenarios)
    def test_collect_data(self, scenario_params, tested_object):
        """Test OperatingSystemDiskSize collect_data()."""
        DataCollectorTestBase.test_collect_data(self, scenario_params, tested_object)
