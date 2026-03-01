"""
Linux rule domain for OpenShift cluster.

Orchestrates Linux system healthcheck validators.
Based on support/HealthChecks/flows/Linux/Linux_validations.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.linux.linux_validations import (
    AuditdBacklogLimit,
    ClockSynchronized,
    IsHostReachable,
    SelinuxMode,
    SystemdServicesStatus,
    TooManyOpenFilesCheck,
    VerifyDuNotHang,
    YumlockFileCheck,
)


class LinuxValidationDomain(RuleDomain):
    """
    Linux rule domain for OpenShift.

    Validates Linux-specific health on cluster nodes.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "linux"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of Linux validators to run.

        Returns:
            List of Rule classes (ported from HC Linux_validations.py)
        """
        return [
            SystemdServicesStatus,
            IsHostReachable,
            ClockSynchronized,
            TooManyOpenFilesCheck,
            SelinuxMode,
            AuditdBacklogLimit,
            VerifyDuNotHang,
            YumlockFileCheck,
        ]
