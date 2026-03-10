"""Profiles configuration for managing rule dependencies."""

import json


class Profiles(dict):
    """Profiles configuration mapping profile names to their included dependencies.

    Inherits from dict[str, set[str]] where:
    - key: profile name
    - value: set of all transitive dependencies (flat, fully resolved)

    Dependencies are resolved at load time by ProfileLoader, which flattens
    the dependency tree and detects circular dependencies.
    """

    def __getitem__(self, key: str) -> set:
        """Get profile dependencies with helpful error message.

        Args:
            key: Profile name.

        Returns:
            Set of all transitive dependencies.

        Raises:
            KeyError: If profile doesn't exist, with list of available profiles.
        """
        if key not in self:
            available = self.format_profiles()
            raise KeyError(
                f"Profile '{key}' not found.\n\n"
                f"Available profiles:\n{available}"
            )
        return super().__getitem__(key)

    def format_profiles(self) -> str:
        """Format profiles as a JSON-formatted dict representation.

        Returns:
            JSON-formatted string representation of the profile dict.
        """
        if not self:
            return "{}"

        # Convert sets to sorted lists for JSON serialization
        regular_dict = {
            name: sorted(super().__getitem__(name))
            for name in sorted(self.keys())
        }
        return json.dumps(regular_dict, indent=4)

    def __str__(self) -> str:
        """Return formatted string representation."""
        return self.format_profiles()

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"<Profiles with {len(self)} profile(s)>"
