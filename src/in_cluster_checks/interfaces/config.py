"""Configuration dataclass for in-cluster-checks framework."""

from dataclasses import dataclass


@dataclass
class InClusterCheckConfig:
    """Configuration for in-cluster check execution."""

    # Debug settings
    debug_rule_flag: bool = False
    debug_rule_name: str = ""

    # Execution settings
    parallel_execution: bool = True
    max_workers: int = 10
    command_timeout: int = 120

    # Secret filtering
    filter_secrets: bool = True
