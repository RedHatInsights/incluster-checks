"""
Secret filter for sanitizing commands and output before logging.

Adapted from support's HealthCheckCommon/secret_filter.py.
Removes sensitive data like passwords, tokens, API keys from strings before logging.
"""

import re
from typing import List, Union


class SecretFilter:
    """Filter sensitive data from strings before logging."""

    # Keywords that indicate potential secrets
    tokens_of_secrets = [
        "openssl",
        "-u root",
        "pass",
        "password",
        "rabbit",
        "--decode",
        "cookie hash",
        "secret",
        "admin_pwd",
        "ipmitool",
        "token",
        "api_key",
        "apikey",
    ]

    # Regex patterns to match and replace sensitive data
    # Each pattern captures the sensitive part in group 1
    patterns_of_secrets = [
        # Base64 encoded secrets
        r"echo\s([a-zA-Z0-9=]+)\s\|\sbase64 -d",
        # MySQL password arguments
        r"mysql.* -p([a-zA-Z0-9]+)\s",
        r"mysql.* -p\s([a-zA-Z0-9]+)\s",
        # Auth tokens in headers
        r"\sX-Auth-Token:([a-zA-Z0-9_\\-]+)\s",
        r"Authorization:\s*Bearer\s+([a-zA-Z0-9_\\-]+)",
        # URLs with credentials (://user:password@host)
        r"://[a-zA-Z]*:([a-zA-Z0-9]+)@",
        r"://.*,[a-zA-Z]*:([a-zA-Z0-9]+)@",
        # Redis CLI password
        r"redis-cli.*\s-a\s'([a-zA-Z0-9]+)'",
        # Generic password/secret/token arguments
        r"(?:--password|--secret|--token)[=\s]+['\"]?([a-zA-Z0-9_\\-]+)['\"]?",
    ]

    REDACTED_MSG = "[REDACTED]"

    @staticmethod
    def filter_string_array(input_string_array: Union[str, List[str], None]) -> Union[str, List[str], None]:
        """
        Filter secrets from string or list of strings.

        Args:
            input_string_array: String or list of strings to filter

        Returns:
            Filtered string or list with sensitive data replaced by [REDACTED]
        """
        if input_string_array is None:
            return input_string_array

        str_flag = False
        if isinstance(input_string_array, str):
            input_string_array = [input_string_array]
            str_flag = True

        assert isinstance(input_string_array, list)

        out_array = []
        for line in input_string_array:
            if line is None:
                filtered = None
            elif isinstance(line, list):
                filtered = SecretFilter.filter_string_array(line)
            else:
                filtered = SecretFilter.filter_regex(line)
                filtered = SecretFilter.filter_basic(filtered)

            out_array.append(filtered)

        return out_array if not str_flag else out_array[0]

    @staticmethod
    def filter_regex(input_string: str) -> str:
        """
        Filter sensitive data using regex patterns.

        Args:
            input_string: String to filter

        Returns:
            String with sensitive parts replaced by [REDACTED]
        """
        assert isinstance(input_string, str)

        out_string = input_string
        for pattern in SecretFilter.patterns_of_secrets:
            # Find all matches
            matches = re.findall(pattern, out_string)
            for match in matches:
                # Replace the sensitive part with [REDACTED]
                out_string = out_string.replace(match, SecretFilter.REDACTED_MSG)

        return out_string

    @staticmethod
    def filter_basic(input_variable: str) -> str:
        """
        Basic token-based filtering.

        If any token from tokens_of_secrets is found in the string,
        mark it as potentially sensitive.

        Args:
            input_variable: String to check

        Returns:
            Original string or [REDACTED] if tokens found
        """
        for token in SecretFilter.tokens_of_secrets:
            if token in input_variable:
                # If the string contains a secret token, consider the whole command sensitive
                # Only redact if it looks like it contains actual secrets (not just the word "password")
                if any(pattern_match in input_variable for pattern_match in ["=", ":", "-p", "Bearer"]):
                    return SecretFilter.REDACTED_MSG

        return input_variable

    @staticmethod
    def sanitize(input_data: Union[str, List[str], None]) -> Union[str, List[str], None]:
        """
        Convenience method to sanitize strings before logging.

        Args:
            input_data: String or list of strings to sanitize

        Returns:
            Sanitized data safe for logging
        """
        return SecretFilter.filter_string_array(input_data)
