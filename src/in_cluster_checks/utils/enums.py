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
    ONE_WORKER = "ONE_WORKER"

    @staticmethod
    def get_all_single_types():
        """
        Get all objective types that represent single hosts.

        These are objectives that run on exactly one node, as opposed to
        multiple nodes (e.g., ALL_NODES, MASTERS, WORKERS).

        Returns:
            List of single-host objective strings

        Note:
            Used by DataCollector to validate many-to-many relationships
            are not created. Data collectors only support:
            - one-to-one (single source -> single target)
            - many-to-one (multiple sources -> single target)
        """
        return [
            Objectives.ORCHESTRATOR,
            Objectives.ONE_MASTER,
            Objectives.ONE_WORKER,
        ]

    @staticmethod
    def get_multi_type_for_single(single_type: str) -> str | None:
        """
        Map a single-instance objective to its corresponding multi-node objective.

        This mapping is used when creating rule instances with ONE_* objectives.
        The domain needs to find nodes with the corresponding multi-node role
        and create only ONE instance from those nodes.

        Args:
            single_type: Single-instance objective (e.g., ONE_MASTER)

        Returns:
            Corresponding multi-node objective (e.g., MASTERS), or None if not applicable

        Examples:
            ONE_MASTER -> MASTERS
            ONE_WORKER -> WORKERS
            ORCHESTRATOR -> None (no multi-node equivalent)
        """
        mapping = {
            Objectives.ONE_MASTER: Objectives.MASTERS,
            Objectives.ONE_WORKER: Objectives.WORKERS,
        }
        return mapping.get(single_type)


# Orchestrator host identifiers (not a real cluster node)
ORCHESTRATOR_HOST_NAME = "in-cluster-orchestrator"
ORCHESTRATOR_HOST_IP = "127.0.0.1"


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
