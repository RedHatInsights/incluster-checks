"""Global configuration for in-cluster checks."""

from profiles.loader import ProfileLoader
from profiles.profile import Profiles

# Global configuration values
debug_rule_flag: bool = False
debug_rule_name: str = ""
max_workers: int = 50
profiles_hierarchy = Profiles()
active_profile: str = ""  # Must be set via set_config() - no default


def set_config(
    active_profile_val: str,
    debug_rule_flag_val: bool = False,
    debug_rule_name_val: str = "",
    max_workers_val: int = 50,
):
    """Update global configuration values.

    Args:
        active_profile_val: Active profile name (required, no default)
        debug_rule_flag_val: Enable debug mode for detailed output
        debug_rule_name_val: Name of specific rule to run in debug mode
        max_workers_val: Maximum number of concurrent workers

    Raises:
        ValueError: If active_profile_val is not provided or is empty
    """
    global debug_rule_flag, debug_rule_name, max_workers, profiles_hierarchy, active_profile

    # Validate active_profile is set
    if not active_profile_val:
        raise ValueError("active_profile must be provided and cannot be empty")

    debug_rule_flag = debug_rule_flag_val
    debug_rule_name = debug_rule_name_val
    max_workers = max_workers_val
    active_profile = active_profile_val
    profiles_hierarchy = Profiles()
    ProfileLoader.load(profiles_hierarchy)
