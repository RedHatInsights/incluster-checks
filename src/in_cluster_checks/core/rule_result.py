"""
Result dataclasses for rule execution.

Contains RuleResult and PrerequisiteResult classes used across the rule system.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from in_cluster_checks.utils.enums import Status


@dataclass
class RuleResult:
    """
    Result of a rule check with optional structured data.

    Supports both simple text results and rich structured data for advanced use cases
    like Blueprint hardware analysis, tables, charts, etc.
    """

    status: Status
    message: Optional[str] = None
    system_info: Optional[Dict[str, Any]] = None  # Main structured data (dict)
    table_data: Optional[list] = None  # Table rows
    table_headers: Optional[list] = None  # Table column headers
    remarks: Optional[str] = None  # Additional notes/remarks
    extra: Optional[Dict[str, Any]] = None  # Extra fields not shown in regular HTML view

    def __bool__(self) -> bool:
        """Return True if rule passed, False otherwise."""
        return self.status == Status.PASSED

    @staticmethod
    def passed(message: str = "", system_info: Optional[Dict[str, Any]] = None, **extra):
        """Create a PASSED result with optional extra fields."""
        return RuleResult(Status.PASSED, message, system_info=system_info, extra=extra or None)

    @staticmethod
    def failed(message: str, system_info: Optional[Dict[str, Any]] = None, **extra):
        """Create a FAILED result with optional extra fields."""
        return RuleResult(Status.FAILED, message, system_info=system_info, extra=extra or None)

    @staticmethod
    def warning(message: str, system_info: Optional[Dict[str, Any]] = None, **extra):
        """Create a WARNING result with optional extra fields."""
        return RuleResult(Status.WARNING, message, system_info=system_info, extra=extra or None)

    @staticmethod
    def info(message: str = "", system_info: Optional[Dict[str, Any]] = None, **extra):
        """
        Create an INFO result.

        Args:
            message: Short summary message (shown in main view)
            system_info: Main structured data (dict) for JSON output
            **extra: Extra fields not shown in regular HTML view
                    Examples:
                    - html_tab: Name of HTML tab to link to ("blueprint")
                    - is_uniform: Boolean flag for quick checks
                    - chart_data: Data for rendering charts
        """
        return RuleResult(Status.INFO, message, system_info=system_info, extra=extra or None)

    @staticmethod
    def skip(message: str):
        """
        Create a SKIP result.

        Use when a rule is skipped due to an exception or error during execution.
        This indicates the check could not complete due to unexpected runtime issues.

        Example: A rule that fails due to a command timeout or execution error.
        """
        return RuleResult(Status.SKIP, message)

    @staticmethod
    def not_applicable(message: str):
        """
        Create a NOT_APPLICABLE result.

        Use when a rule cannot run because its prerequisite is not met.
        This indicates the check is not relevant for the current environment/configuration.

        Example: A hardware rule that requires a specific device that doesn't exist on the node.
        """
        return RuleResult(Status.NOT_APPLICABLE, message)


@dataclass
class PrerequisiteResult:
    """Result of a prerequisite check."""

    fulfilled: bool
    message: str = ""

    @staticmethod
    def met(message: str = ""):
        """Create a result indicating prerequisite is met."""
        return PrerequisiteResult(True, message)

    @staticmethod
    def not_met(message: str):
        """Create a result indicating prerequisite is not met."""
        return PrerequisiteResult(False, message)
