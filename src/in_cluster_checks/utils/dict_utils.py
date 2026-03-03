"""
Utilities for dictionary operations.

Provides helper functions for dict serialization and manipulation.
"""

import json


def convert_dict_to_sorted_json_str(data_dict: dict) -> str:
    """
    Convert dictionary to sorted JSON string for cache key generation.

    Adapted from HealthChecks python_utils.convert_dict_to_str_sort_keys().
    Used by ParallelRunner for deterministic cache key generation in
    many-to-one data collector relationships.

    Args:
        data_dict: Dictionary to convert (typically collector kwargs)

    Returns:
        JSON string with sorted keys for deterministic lookup

    Example:
        >>> convert_dict_to_sorted_json_str({"b": 2, "a": 1})
        '{"a": 1, "b": 2}'
    """
    return json.dumps(data_dict, sort_keys=True)
