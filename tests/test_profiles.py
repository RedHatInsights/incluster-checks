"""Unit tests for profiles module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.profiles.loader import ProfileLoader
from src.profiles.profile import Profiles


@pytest.fixture
def mock_profiles_yaml():
    """Create a mock profiles.yaml file for testing.

    Structure:
    - general: base level (no dependencies)
    - telco: includes general, rh-nokia, telco-base
    - rh-nokia: includes general, telco-base
    - telco-base: includes general
    - ai: includes ai-base, gpu, general
    - ai-base: includes general
    - gpu: includes general
    - nvidia: includes ai, general
    """
    config = {
        "profiles": {
            "general": None,
            "telco": {
                "include": ["general", "rh-nokia", "telco-base"]
            },
            "rh-nokia": {
                "include": ["general", "telco-base"]
            },
            "telco-base": {
                "include": ["general"]
            },
            "ai": {
                "include": ["ai-base", "gpu"]
            },
            "ai-base": {
                "include": ["general"]
            },
            "gpu": {
                "include": ["general"]
            },
            "nvidia": {
                "include": ["ai", "general"]
            },
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


class TestProfileLoader:
    """Test ProfileLoader functionality."""

    def test_general_is_base_profile(self, mock_profiles_yaml):
        """Test that 'general' profile is the base with no dependencies."""
        profile = Profiles()
        ProfileLoader.load(profile, mock_profiles_yaml)

        # General should only include itself (no other dependencies)
        general_includes = profile["general"]
        assert general_includes == {"general"}, (
            f"'general' profile should only include itself. "
            f"Got: {sorted(general_includes)}"
        )

        # Verify all profiles include themselves and general (directly or transitively)
        for profile_name in profile.keys():
            profile_includes = profile[profile_name]
            assert profile_name in profile_includes, (
                f"Profile '{profile_name}' should include itself. "
                f"Includes: {sorted(profile_includes)}"
            )
            assert "general" in profile_includes, (
                f"Profile '{profile_name}' should include 'general'. "
                f"Includes: {sorted(profile_includes)}"
            )

    def test_recursion_3_levels(self, mock_profiles_yaml):
        """Test that recursion works up to 3 levels deep.

        Example path: telco -> rh-nokia -> telco-base -> general
        """
        profile = Profiles()
        ProfileLoader.load(profile, mock_profiles_yaml)

        # Test 'telco' resolved dependencies
        telco_deps = profile["telco"]
        assert "general" in telco_deps  # Direct include
        assert "rh-nokia" in telco_deps  # Direct include
        assert "telco-base" in telco_deps  # Transitive (via rh-nokia)

        # Test 'rh-nokia' resolved dependencies
        rh_nokia_deps = profile["rh-nokia"]
        assert "general" in rh_nokia_deps  # Direct include
        assert "telco-base" in rh_nokia_deps  # Direct include

        # Test 'telco-base' resolved dependencies
        telco_base_deps = profile["telco-base"]
        assert "general" in telco_base_deps  # Direct include
        assert "telco-base" in telco_base_deps  # Includes itself
        assert len(telco_base_deps) == 2  # Includes general and itself

        # Test 'general' only includes itself
        general_deps = profile["general"]
        assert general_deps == {"general"}  # Only includes itself

    def test_non_existent_profile_raises_exception(self, mock_profiles_yaml):
        """Test that accessing a non-existent profile raises KeyError."""
        profile = Profiles()
        ProfileLoader.load(profile, mock_profiles_yaml)

        with pytest.raises(KeyError) as exc_info:
            _ = profile["non_existent_profile"]

        error_message = str(exc_info.value)
        assert "non_existent_profile" in error_message
        assert "not found" in error_message
        assert "Available profiles" in error_message

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are detected and raise ValueError."""
        config = {
            "profiles": {
                "a": {"include": ["b"]},
                "b": {"include": ["c"]},
                "c": {"include": ["a"]},  # Creates cycle: a -> b -> c -> a
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            profile = Profiles()
            with pytest.raises(ValueError) as exc_info:
                ProfileLoader.load(profile, temp_path)

            error_message = str(exc_info.value)
            assert "Circular dependency" in error_message
        finally:
            Path(temp_path).unlink()

    def test_missing_dependency_raises_exception(self):
        """Test that referencing undefined profile raises KeyError."""
        config = {
            "profiles": {
                "valid": {"include": ["undefined_profile"]},
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        try:
            profile = Profiles()
            with pytest.raises(KeyError) as exc_info:
                ProfileLoader.load(profile, temp_path)

            error_message = str(exc_info.value)
            assert "undefined_profile" in error_message
        finally:
            Path(temp_path).unlink()

    def test_empty_profile_has_no_dependencies(self, mock_profiles_yaml):
        """Test that profile with no includes only includes itself."""
        profile = Profiles()
        ProfileLoader.load(profile, mock_profiles_yaml)

        general_deps = profile["general"]
        assert general_deps == {"general"}
        assert len(general_deps) == 1

    def test_transitive_dependencies_no_duplicates(self, mock_profiles_yaml):
        """Test that transitive dependencies don't create duplicates.

        Example: 'ai' includes both 'ai-base' and 'gpu', and both include 'general'.
        'general' should only appear once in the resolved set.
        """
        profile = Profiles()
        ProfileLoader.load(profile, mock_profiles_yaml)

        ai_deps = profile["ai"]

        # Count how many times 'general' appears (should be 1)
        general_count = list(ai_deps).count("general")
        assert general_count == 1, "Transitive dependencies should not create duplicates"

        # Verify ai includes itself, ai-base, gpu, and general (transitively)
        assert "ai" in ai_deps  # Includes itself
        assert "ai-base" in ai_deps
        assert "gpu" in ai_deps
        assert "general" in ai_deps
        assert len(ai_deps) == 4

    def test_get_available_profiles(self, mock_profiles_yaml):
        """Test getting list of available profiles without resolution."""
        available = ProfileLoader.get_available_profiles(mock_profiles_yaml)

        # Should return sorted list of profile names
        assert isinstance(available, list)
        assert available == sorted(available)  # Verify it's sorted

        # Should contain all profiles from the mock YAML
        expected_profiles = ['ai', 'ai-base', 'general', 'gpu', 'nvidia', 'rh-nokia', 'telco', 'telco-base']
        assert available == expected_profiles


class TestRuleProfileEnablement:
    """Test Rule.is_enabled_for_active_profile() functionality."""

    @pytest.fixture
    def rule_profiles_yaml(self):
        """Create a mock profiles.yaml file for rule enablement testing.

        Structure (independent copy to avoid coupling with real profiles.yaml):
        - general: base level (no dependencies)
        - telco: includes general, rh-nokia, telco-base
        - rh-nokia: includes general, telco-base
        - telco-base: includes general
        - ai: includes ai-base, gpu
        - ai-base: includes general
        - gpu: includes general
        - nvidia: includes ai, general
        """
        config = {
            "profiles": {
                "general": None,
                "telco": {
                    "include": ["general", "rh-nokia", "telco-base"]
                },
                "rh-nokia": {
                    "include": ["general", "telco-base"]
                },
                "telco-base": {
                    "include": ["general"]
                },
                "ai": {
                    "include": ["ai-base", "gpu"]
                },
                "ai-base": {
                    "include": ["general"]
                },
                "gpu": {
                    "include": ["general"]
                },
                "nvidia": {
                    "include": ["ai", "general"]
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink()

    @pytest.fixture
    def loaded_profiles(self, rule_profiles_yaml):
        """Load profiles for testing."""
        from in_cluster_checks import global_config

        profile = Profiles()
        ProfileLoader.load(profile, rule_profiles_yaml)
        global_config.profiles_hierarchy = profile
        global_config.active_profile = "general"
        return profile

    def test_default_rule_runs_for_all_profiles(self, loaded_profiles):
        """Test that default rule (supported_profiles={'general'}) runs for all profiles."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class DefaultRule(Rule):
            title = "Default Rule"
            supported_profiles = {'general'}

            def run_rule(self):
                pass

        # Default rule should run for all profiles since all include 'general'
        for profile_name in loaded_profiles.keys():
            global_config.active_profile = profile_name
            assert DefaultRule.is_enabled_for_active_profile() is True, (
                f"Default rule should run for '{profile_name}' profile"
            )

    def test_nvidia_rule_only_runs_for_nvidia_ai(self, loaded_profiles):
        """Test that nvidia-specific rule only runs for nvidia/ai profiles."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class NvidiaRule(Rule):
            title = "Nvidia Rule"
            supported_profiles = {'nvidia', 'ai'}

            def run_rule(self):
                pass

        # Should run for nvidia and ai
        for profile_name in ['nvidia', 'ai']:
            global_config.active_profile = profile_name
            assert NvidiaRule.is_enabled_for_active_profile() is True, (
                f"Nvidia rule should run for '{profile_name}' profile"
            )

        # Should NOT run for general or telco
        for profile_name in ['general', 'telco', 'rh-nokia']:
            global_config.active_profile = profile_name
            assert NvidiaRule.is_enabled_for_active_profile() is False, (
                f"Nvidia rule should NOT run for '{profile_name}' profile"
            )

    def test_telco_rule_only_runs_for_telco(self, loaded_profiles):
        """Test that telco-specific rule only runs for telco profiles."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class TelcoRule(Rule):
            title = "Telco Rule"
            supported_profiles = {'telco'}

            def run_rule(self):
                pass

        # Should run for telco
        global_config.active_profile = 'telco'
        assert TelcoRule.is_enabled_for_active_profile() is True

        # Should NOT run for general, nvidia, or rh-nokia
        for profile_name in ['general', 'nvidia', 'rh-nokia', 'ai']:
            global_config.active_profile = profile_name
            assert TelcoRule.is_enabled_for_active_profile() is False, (
                f"Telco rule should NOT run for '{profile_name}' profile"
            )

    def test_multi_profile_rule(self, loaded_profiles):
        """Test rule that supports multiple profiles."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class MultiRule(Rule):
            title = "Multi Profile Rule"
            supported_profiles = {'ai-base', 'gpu', 'telco-base'}

            def run_rule(self):
                pass

        # Should run for profiles that include ai-base, gpu, or telco-base
        test_cases = {
            'ai': True,        # includes ai-base and gpu
            'gpu': True,       # includes gpu
            'nvidia': True,    # includes ai-base and gpu
            'telco': True,     # includes telco-base
            'rh-nokia': True,  # includes telco-base
            'general': False,  # doesn't include any of the supported profiles
        }

        for profile_name, should_run in test_cases.items():
            global_config.active_profile = profile_name
            result = MultiRule.is_enabled_for_active_profile()
            assert result is should_run, (
                f"Multi rule should {'run' if should_run else 'NOT run'} "
                f"for '{profile_name}' profile (got {result})"
            )

    def test_transitive_inclusion(self, loaded_profiles):
        """Test that rules work with transitive profile inclusion."""
        from in_cluster_checks import global_config
        from in_cluster_checks.core.rule import Rule

        class TelcoBaseRule(Rule):
            title = "Telco Base Rule"
            supported_profiles = {'telco-base'}

            def run_rule(self):
                pass

        # telco-base is transitively included by telco and rh-nokia
        for profile_name in ['telco', 'rh-nokia', 'telco-base']:
            global_config.active_profile = profile_name
            assert TelcoBaseRule.is_enabled_for_active_profile() is True, (
                f"Telco-base rule should run for '{profile_name}' profile "
                "(telco-base is included transitively)"
            )

        # Should NOT run for ai/nvidia/general
        for profile_name in ['general', 'ai', 'nvidia']:
            global_config.active_profile = profile_name
            assert TelcoBaseRule.is_enabled_for_active_profile() is False, (
                f"Telco-base rule should NOT run for '{profile_name}' profile"
            )


class TestGlobalConfig:
    """Test global_config.set_config() functionality."""

    def test_set_config_requires_active_profile(self):
        """Test that set_config() raises ValueError when active_profile is empty."""
        from in_cluster_checks import global_config

        with pytest.raises(ValueError) as exc_info:
            global_config.set_config(active_profile_val="")

        error_message = str(exc_info.value)
        assert "active_profile" in error_message
        assert "cannot be empty" in error_message

    def test_set_config_with_valid_profile(self):
        """Test that set_config() works correctly with a valid profile."""
        from in_cluster_checks import global_config

        # Should not raise any exception
        global_config.set_config(active_profile_val="general")

        # Verify values are set
        assert global_config.active_profile == "general"
        assert len(global_config.profiles_hierarchy) > 0
        assert "general" in global_config.profiles_hierarchy

    def test_set_config_with_custom_profile(self):
        """Test that set_config() works with different profile values."""
        from in_cluster_checks import global_config

        # Test with nvidia profile
        global_config.set_config(active_profile_val="nvidia")
        assert global_config.active_profile == "nvidia"

        # Test with telco profile
        global_config.set_config(active_profile_val="telco")
        assert global_config.active_profile == "telco"
