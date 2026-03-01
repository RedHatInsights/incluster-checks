"""
Enums for in-cluster rule checks.

Adapted from support/HealthChecks/tools/global_enums.py
Simplified for OpenShift use case.
"""

from enum import Enum


class Objectives:
    """
    Execution objectives (targets) for validations.

    Defines where/how validations should run in OpenShift context.
    """

    # Special objective for orchestrator validators (no host execution)
    ORCHESTRATOR = "ORCHESTRATOR"  # Coordinates data collection across nodes

    # Node-level execution (via oc debug node/<name>)
    ALL_NODES = "ALL_NODES"
    MASTERS = "MASTERS"
    WORKERS = "WORKERS"
    MANAGERS = "MANAGERS"  # Control plane nodes
    EDGES = "EDGES"
    APP_WORKERS = "APP_WORKERS"  # NCP-specific app worker nodes
    INFRA = "INFRA"  # Infrastructure nodes
    MONITORS = "MONITORS"  # Monitoring nodes
    MAINTENANCE = "MAINTENANCE"  # Nodes in maintenance mode

    # Single node from group
    ONE_MASTER = "ONE_MASTER"
    ONE_MANAGER = "ONE_MANAGER"
    ONE_WORKER = "ONE_WORKER"


class Status(str, Enum):
    """
    Validation status types.

    Status values for rule results.
    """

    PASSED = "pass"  # Validation passed successfully
    FAILED = "fail"  # Validation failed (critical issue)
    WARNING = "warning"  # Validation found issues but not critical
    INFO = "info"  # Informational only, no validation
    SKIP = "skip"  # Skipped due to exception
    NOT_APPLICABLE = "na"  # Not applicable (prerequisite not passed)

    # Exception classification types (internal use)
    SYS_PROBLEM = "SYS_PROBLEM"  # UnExpectedSystemOutput exception
    NO_HOST_FOUND = "NO_HOST_FOUND"  # NoSuitableHostWasFoundForRoles exception
