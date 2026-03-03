"""Global configuration for in-cluster checks."""

# Global configuration values
debug_rule_flag: bool = False
debug_rule_name: str = ""
max_workers: int = 50


def set_config(
    debug_rule_flag_val: bool = False,
    debug_rule_name_val: str = "",
    max_workers_val: int = 50,
):
    """Update global configuration values."""
    global debug_rule_flag, debug_rule_name, max_workers
    debug_rule_flag = debug_rule_flag_val
    debug_rule_name = debug_rule_name_val
    max_workers = max_workers_val
