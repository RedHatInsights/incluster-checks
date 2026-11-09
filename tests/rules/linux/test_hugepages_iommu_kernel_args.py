"""Tests for AreHugepagesIommuKernelArgsSet rule."""

import pytest

from in_cluster_checks.rules.linux.linux_validations import AreHugepagesIommuKernelArgsSet
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleScenarioParams,
    RuleTestBase,
)


class TestAreHugepagesIommuKernelArgsSet(RuleTestBase):
    """Test AreHugepagesIommuKernelArgsSet rule."""

    tested_type = AreHugepagesIommuKernelArgsSet

    validation_cmd = "cat /proc/cmdline"

    cmdline_all_args_present = (
        "BOOT_IMAGE=(hd0,gpt3)/ostree/rhcos/vmlinuz-5.14.0-427.el9.x86_64"
        " root=UUID=abc123 rw rootflags=subvol=root"
        " module_blacklist=irdma default_hugepagesz=1G hugepagesz=1G hugepages=16"
        " intel_iommu=on iommu=pt pci=realloc=on"
    )

    cmdline_missing_all = (
        "BOOT_IMAGE=(hd0,gpt3)/ostree/rhcos/vmlinuz-5.14.0-427.el9.x86_64"
        " root=UUID=abc123 rw rootflags=subvol=root"
    )

    cmdline_missing_some = (
        "BOOT_IMAGE=(hd0,gpt3)/ostree/rhcos/vmlinuz-5.14.0-427.el9.x86_64"
        " root=UUID=abc123 rw rootflags=subvol=root"
        " module_blacklist=irdma default_hugepagesz=1G hugepagesz=1G hugepages=16"
    )

    cmdline_missing_iommu_only = (
        "BOOT_IMAGE=(hd0,gpt3)/ostree/rhcos/vmlinuz-5.14.0-427.el9.x86_64"
        " root=UUID=abc123 rw rootflags=subvol=root"
        " module_blacklist=irdma default_hugepagesz=1G hugepagesz=1G hugepages=16"
        " intel_iommu=on pci=realloc=on"
    )

    scenario_passed = [
        RuleScenarioParams(
            "all required kernel arguments present",
            {validation_cmd: CmdOutput(cmdline_all_args_present)},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "all kernel arguments missing",
            {validation_cmd: CmdOutput(cmdline_missing_all)},
            failed_msg=(
                "Missing required kernel arguments for Spectrum-X (99-kernel-args-hugepages):"
                " ['module_blacklist=irdma', 'default_hugepagesz=1G', 'hugepagesz=1G',"
                " 'hugepages=16', 'intel_iommu=on', 'iommu=pt', 'pci=realloc=on']"
            ),
        ),
        RuleScenarioParams(
            "some kernel arguments missing (iommu and pci)",
            {validation_cmd: CmdOutput(cmdline_missing_some)},
            failed_msg=(
                "Missing required kernel arguments for Spectrum-X (99-kernel-args-hugepages):"
                " ['intel_iommu=on', 'iommu=pt', 'pci=realloc=on']"
            ),
        ),
        RuleScenarioParams(
            "only iommu=pt missing",
            {validation_cmd: CmdOutput(cmdline_missing_iommu_only)},
            failed_msg=(
                "Missing required kernel arguments for Spectrum-X (99-kernel-args-hugepages):"
                " ['iommu=pt']"
            ),
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
