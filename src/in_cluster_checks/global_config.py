"""Global configuration instance for in-cluster checks."""

from in_cluster_checks.interfaces.config import InClusterCheckConfig

# Global config instance
# This is set by the runner and accessed by other components
config = InClusterCheckConfig()


def set_config(new_config: InClusterCheckConfig):
    """Update global config instance."""
    global config
    config = new_config
