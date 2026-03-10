"""Profiles configuration loader and dependency resolver."""

from pathlib import Path

import yaml

from .profile import Profiles

class ProfileLoader:
    """Load profile configurations from YAML into a Profiles instance."""

    @staticmethod
    def _resolve_and_populate(profiles_instance: Profiles, raw_profiles: dict) -> None:
        """Resolve all dependencies and populate the profiles instance with flat sets.

        Args:
            profiles_instance: Profiles instance to populate.
            raw_profiles: Dictionary of profile configurations from YAML.

        Raises:
            ValueError: If circular dependency detected.
        """
        # First pass: populate with direct includes
        direct_includes = {}
        for name, config in raw_profiles.items():
            if config is None:
                direct_includes[name] = set()
            else:
                includes = config.get("include", [])
                direct_includes[name] = set(includes)

        # Second pass: resolve all transitive dependencies
        profiles_instance.clear()
        for name in direct_includes:
            resolved = ProfileLoader._resolve_recursive(name, direct_includes, set(), [])
            resolved.add(name)  # Add the profile itself to its includes
            profiles_instance[name] = resolved

    @staticmethod
    def _resolve_recursive(
        name: str,
        direct_includes: dict,
        visiting: set,
        path: list,
    ) -> set:
        """Recursively resolve all dependencies for a profile.

        Args:
            name: Profile name to resolve.
            direct_includes: Dictionary mapping profile names to their direct includes.
            visiting: Set of profiles currently being visited (for cycle detection).
            path: Current path in the dependency graph (for error messages).

        Returns:
            Set of all transitive dependencies (not including the profile itself).

        Raises:
            ValueError: If circular dependency detected.
            KeyError: If profile references undefined dependency.
        """
        if name in visiting:
            cycle = " -> ".join(path + [name])
            raise ValueError(f"Circular dependency detected: {cycle}")

        if name not in direct_includes:
            raise KeyError(f"Profile not found: {name}")

        visiting.add(name)
        resolved = set()

        for include in direct_includes[name]:
            resolved.add(include)
            sub_resolved = ProfileLoader._resolve_recursive(
                include, direct_includes, visiting, path + [name]
            )
            resolved.update(sub_resolved)

        visiting.remove(name)
        return resolved

    @staticmethod
    def load(profiles_instance: Profiles, config_path: str | None = None) -> None:
        """Load profile configuration from YAML file into the provided Profiles instance.

        Args:
            profiles_instance: Profiles instance to populate.
            config_path: Path to profiles.yaml. If None, uses default location.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If circular dependency detected.
        """
        if config_path is None:
            config_path = Path(__file__).parent / "profiles.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Profile config not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            raw_profiles = data.get("profiles", {})

        ProfileLoader._resolve_and_populate(profiles_instance, raw_profiles)

    @staticmethod
    def get_available_profiles(config_path: str | None = None) -> list[str]:
        """Get list of available profile names from YAML configuration.

        This method returns profile names without resolving dependencies.
        Useful for listing available profiles for UI/CLI selection.

        Args:
            config_path: Path to profiles.yaml. If None, uses default location.

        Returns:
            Sorted list of available profile names.

        Raises:
            FileNotFoundError: If config file doesn't exist.

        Example:
            >>> ProfileLoader.get_available_profiles()
            ['ai', 'ai-base', 'general', 'gpu', 'nvidia', 'rh-nokia', 'telco', 'telco-base']
        """
        if config_path is None:
            config_path = Path(__file__).parent / "profiles.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Profile config not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
            raw_profiles = data.get("profiles", {})

        return sorted(raw_profiles.keys())
