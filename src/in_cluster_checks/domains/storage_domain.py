"""
Storage rule domain for OpenShift cluster.

Orchestrates storage-related healthcheck validators, particularly for Ceph/Rook storage.
Based on support/HealthChecks/flows/Storage/ceph/Ceph.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.storage.storage_validations import (
    CephOsdTreeWorks,
    IsCephHealthOk,
    IsCephOSDsNearFull,
    IsOSDsUp,
    IsOSDsWeightOK,
)


class StorageValidationDomain(RuleDomain):
    """
    Storage rule domain for OpenShift.

    Validates Ceph/Rook storage health and configuration on cluster nodes.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "storage"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of storage validators to run.

        Returns:
            List of Rule classes (ported from HC Storage validations)
        """
        return [
            CephOsdTreeWorks,
            IsCephHealthOk,
            IsCephOSDsNearFull,
            IsOSDsUp,
            IsOSDsWeightOK,
        ]
