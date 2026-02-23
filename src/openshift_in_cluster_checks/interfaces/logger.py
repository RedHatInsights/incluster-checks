"""Logger interface for openshift-in-cluster-checks framework."""

import logging
from abc import ABC, abstractmethod


class LoggerInterface(ABC):
    """Abstract logger interface for framework components."""

    @abstractmethod
    def debug(self, message: str) -> None:
        """Log debug message."""
        pass

    @abstractmethod
    def info(self, message: str) -> None:
        """Log info message."""
        pass

    @abstractmethod
    def warning(self, message: str) -> None:
        """Log warning message."""
        pass

    @abstractmethod
    def error(self, message: str) -> None:
        """Log error message."""
        pass

    @abstractmethod
    def set_prefix(self, prefix: str) -> None:
        """Set context prefix for logs."""
        pass

    @abstractmethod
    def clear_prefix(self) -> None:
        """Clear context prefix."""
        pass


class StandardLogger(LoggerInterface):
    """Default logger implementation using Python's logging module."""

    def __init__(self, name: str = "openshift_in_cluster_checks", level: int = logging.INFO):
        """
        Initialize standard logger.

        Args:
            name: Logger name
            level: Logging level (default: INFO)
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)

        # Add console handler if none exists
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

        self._prefix = ""

    def debug(self, message: str) -> None:
        """Log debug message."""
        self._logger.debug(self._format(message))

    def info(self, message: str) -> None:
        """Log info message."""
        self._logger.info(self._format(message))

    def warning(self, message: str) -> None:
        """Log warning message."""
        self._logger.warning(self._format(message))

    def error(self, message: str) -> None:
        """Log error message."""
        self._logger.error(self._format(message))

    def set_prefix(self, prefix: str) -> None:
        """Set context prefix for logs."""
        self._prefix = prefix

    def clear_prefix(self) -> None:
        """Clear context prefix."""
        self._prefix = ""

    def _format(self, message: str) -> str:
        """Format message with prefix if set."""
        if self._prefix:
            return f"[{self._prefix}] {message}"
        return message
