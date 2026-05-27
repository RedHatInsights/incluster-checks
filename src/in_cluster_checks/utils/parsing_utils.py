"""
Utilities for parsing command output.

Adapted from support/HealthChecks/tools/python_utils.py
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, Union

import dateutil.parser

from in_cluster_checks.core.exceptions import UnExpectedSystemOutput
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


def parse_json(output: str, cmd: str | SafeCmdString, ip: str) -> Any:
    """
    Parse JSON from command output with detailed error reporting.

    Use this for system/API outputs that should always be valid JSON.
    If JSON parsing fails, it indicates an unexpected system state.

    Args:
        output: JSON string from command
        cmd: Command that produced the output (for error reporting)
        ip: Host IP where command was executed (for error reporting)

    Returns:
        Parsed JSON data (dict, list, etc.)

    Raises:
        UnExpectedSystemOutput: If JSON parsing fails
    """
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        raise UnExpectedSystemOutput(
            ip=ip,
            cmd=cmd,
            output=output,
            message=f"Failed to parse JSON: {e}",
        )


def parse_int(value: str, cmd: str | SafeCmdString, ip: str) -> int:
    """
    Parse integer from command output with detailed error reporting.
    """
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        raise UnExpectedSystemOutput(
            ip=ip,
            cmd=cmd,
            output=value,
            message=f"Failed to parse as integer. "
            f"Expected numeric value, got: {value[:100]!r}. "
            f"Error: {str(e)}",
        )


def parse_datetime(string_datetime: str, cmd: str | SafeCmdString, ip: str) -> datetime:
    """
    Parse datetime string from command output with detailed error reporting.

    Uses dateutil.parser.parse to handle various datetime formats flexibly.

    Args:
        string_datetime: Datetime string from command output
        cmd: Command that produced the output (for error reporting)
        ip: Host IP where command was executed (for error reporting)

    Returns:
        Parsed datetime object

    Raises:
        UnExpectedSystemOutput: If datetime parsing fails
    """
    try:
        return dateutil.parser.parse(string_datetime)
    except (ValueError, dateutil.parser.ParserError) as e:
        raise UnExpectedSystemOutput(
            ip=ip,
            cmd=cmd,
            output=string_datetime,
            message=f"Date/time could not be parsed.\n{str(e)}",
        )


def get_dict_from_string(text: str, delimiter: str = None) -> Dict[str, Union[str, int]]:
    """
    Parse command output into a dictionary of key-value pairs.

    Adapted from healthcheck-backup's PythonUtils.get_dict_from_space_separated_file().
    Parses text with "key: value" or "key value" format.

    Args:
        text: Command output to parse (e.g., from timedatectl, free -m)
        delimiter: Character to split on (default: whitespace)
                  For colon-separated output like "key: value", use delimiter=':'

    Returns:
        Dictionary mapping keys to values (auto-converts values to int when possible)
    """
    result = {}
    delimiter = delimiter or " "

    for line in text.splitlines():
        if not line or delimiter not in line:
            continue

        # Split on first occurrence of delimiter only
        parts = line.split(delimiter, 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()

            # Try to convert to int if possible (like the original implementation)
            try:
                value = int(value)
            except (ValueError, AttributeError):
                # Keep as string if not convertible to int
                value = value.strip()

            result[key] = value

    return result


def format_memory(value: str) -> str:
    """Convert Kubernetes memory value to human-readable format (1-4 digits).

    Args:
        value: Memory value with unit (e.g., "527554188Ki", "25047Mi", "191655242229B")

    Returns:
        Human-readable value in binary units (e.g., "503Gi", "24Gi", "178Gi")
    """
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]+)$", value)
    if not match:
        return value

    num, unit = float(match.group(1)), match.group(2)

    # Binary units (Ki, Mi, Gi, Ti) - Kubernetes standard
    binary_units = {"B": 1, "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}

    if unit not in binary_units:
        return value

    bytes_value = num * binary_units[unit]

    # Find best binary unit (1-4 digits)
    for unit_name, divisor in sorted(binary_units.items(), key=lambda x: x[1], reverse=True):
        if unit_name == "B":
            continue
        converted = bytes_value / divisor
        if 1 <= converted < 10000:
            # Format with 1 decimal, then strip .0 if present
            formatted = f"{converted:.1f}"
            if formatted.endswith(".0"):
                formatted = formatted[:-2]
            return f"{formatted}{unit_name}"

    return value


def format_cpu(value: str) -> str:
    """Convert Kubernetes CPU value to human-readable format.

    Args:
        value: CPU value with unit (e.g., "8 cores", "7500m", "15500m")

    Returns:
        Human-readable value (e.g., "8 cores", "7 cores", "15.5 cores")
    """
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]+)$", value)
    if not match:
        return value

    num, unit = float(match.group(1)), match.group(2)

    if unit == "cores":
        return value
    if unit == "m" and num >= 1000:
        cores = num / 1000
        # Format with 1 decimal, then strip .0 if present
        formatted = f"{cores:.1f}"
        if formatted.endswith(".0"):
            formatted = formatted[:-2]
        return f"{formatted} cores"

    return value
