"""
Etcd rule domain for OpenShift clusters.

Orchestrates etcd-related healthcheck validators.
Based on support/HealthChecks/flows/Etcd/etcd_validations.py
"""

from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.etcd.etcd_validations import (
    EtcdAlarmCheck,
    EtcdBackendCommitPerformanceCheck,
    EtcdBasicCheck,
    EtcdEndpointHealthCheck,
    EtcdLeaderCheck,
    EtcdMemberCountCheck,
    EtcdWalFsyncPerformanceCheck,
    EtcdWriteReadCycleCheck,
)


class EtcdValidationDomain(RuleDomain):
    """
    Etcd rule domain for OpenShift.

    Validates etcd health, performance, and configuration on OpenShift clusters.
    Includes basic connectivity checks, cluster health checks, and performance monitoring.
    """

    def domain_name(self) -> str:
        """Get domain name."""
        return "etcd"

    def get_rule_classes(self) -> List[type]:
        """
        Get list of etcd validators to run.

        Returns:
            List of Rule classes (ported from HC etcd_validations.py)
        """
        return [
            EtcdBasicCheck,
            EtcdAlarmCheck,
            EtcdMemberCountCheck,
            EtcdLeaderCheck,
            EtcdEndpointHealthCheck,
            EtcdWriteReadCycleCheck,
            EtcdWalFsyncPerformanceCheck,
            EtcdBackendCommitPerformanceCheck,
        ]
