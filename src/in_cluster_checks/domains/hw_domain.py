"""
Hardware rule domain for OpenShift cluster.

Orchestrates hardware-related healthcheck validators.
Based on support/HealthChecks/flows/HW/HW_validations.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.hw.hw_validations import (
    BasicFreeMemoryValidation,
    CheckDiskUsage,
    CPUfreqScalingGovernorValidation,
    CpuSpeedValidation,
    HwSysClockCompare,
    TemperatureValidation,
)


class HWValidationDomain(RuleDomain):
    """
    Hardware rule domain for OpenShift.

    Validates CPU, memory, and hardware health on cluster nodes.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "hardware"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of hardware validators to run.

        Returns:
            List of Rule classes (ported from HC HW_validations.py)
        """
        return [
            CheckDiskUsage,
            BasicFreeMemoryValidation,
            CPUfreqScalingGovernorValidation,
            TemperatureValidation,
            CpuSpeedValidation,
            HwSysClockCompare,
        ]
