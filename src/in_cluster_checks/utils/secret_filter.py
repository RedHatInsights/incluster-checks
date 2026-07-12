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
    # Each pattern is compiled with re.IGNORECASE for case-insensitive matching
    # Patterns that need to capture groups use non-capturing groups (?:...) for structure
    # and capturing groups (...) for the sensitive part to be replaced
    patterns_of_secrets = [
        # Kubernetes ServiceAccount JWT (eyJ... format with dots)
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", re.IGNORECASE),
        # OpenShift session token (sha256~... format, 43 chars after tilde)
        re.compile(r"sha256~[A-Za-z0-9_-]{43}", re.IGNORECASE),
        # IPMI password with -P flag
        re.compile(r"ipmitool.*\s-P\s+(\S+)", re.IGNORECASE),
        # kubeconfig certificate and key data
        re.compile(r"client-certificate-data:\s*\S+", re.IGNORECASE),
        re.compile(r"client-key-data:\s*\S+", re.IGNORECASE),
        # PEM private keys (multi-line blocks)
        re.compile(
            r"-----BEGIN\s+.*PRIVATE\s+KEY-----.*?-----END\s+.*PRIVATE\s+KEY-----",
            re.IGNORECASE | re.DOTALL,
        ),
        # Base64 encoded secrets
        re.compile(r"echo\s([a-zA-Z0-9+/=]+)\s\|\sbase64 -d", re.IGNORECASE),
        # MySQL password arguments
        re.compile(r"mysql.* -p(\S+)", re.IGNORECASE),
        re.compile(r"mysql.* -p\s(\S+)", re.IGNORECASE),
        # Auth tokens in headers
        re.compile(r"\sX-Auth-Token:(\S+)", re.IGNORECASE),
        re.compile(r"Authorization:\s*Bearer\s+(\S+)", re.IGNORECASE),
        # URLs with credentials (://user:password@host)
        re.compile(r"://[^:]*:([^@]+)@", re.IGNORECASE),
        re.compile(r"://.*,[^:]*:([^@]+)@", re.IGNORECASE),
        # Redis CLI password
        re.compile(r"redis-cli.*\s-a\s'([^']+)'", re.IGNORECASE),
        # Generic password/secret/token arguments
        re.compile(r"(?:--password|--secret|--token)[=\s]+(\S+)", re.IGNORECASE),
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
            # For compiled patterns, use search and sub
            if hasattr(pattern, "search"):
                # If pattern has groups, replace the matched group
                # Otherwise replace the entire match
                matches = pattern.findall(out_string)
                for match in matches:
                    # Handle both tuple results (from groups) and string results
                    if isinstance(match, tuple):
                        # Pattern has groups, replace each group
                        for group in match:
                            if group:
                                out_string = out_string.replace(group, SecretFilter.REDACTED_MSG)
                    else:
                        # Pattern matches entire string, replace the whole match
                        out_string = out_string.replace(match, SecretFilter.REDACTED_MSG)
            else:
                # Backward compatibility for string patterns (shouldn't happen now)
                matches = re.findall(pattern, out_string)
                for match in matches:
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
        input_lower = input_variable.lower()
        for token in SecretFilter.tokens_of_secrets:
            if token in input_lower:
                # If the string contains a secret token, consider the whole command sensitive
                # Only redact if it looks like it contains actual secrets (not just the word "password")
                if any(pattern_match in input_lower for pattern_match in ["=", ":", "-p", "bearer"]):
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
