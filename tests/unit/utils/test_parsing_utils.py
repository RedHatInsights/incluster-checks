"""Tests for parsing_utils - format_memory and format_cpu."""

import pytest

from in_cluster_checks.utils.parsing_utils import format_cpu, format_memory


class TestFormatMemory:
    """Test format_memory function."""

    def test_ki_to_gi_conversion(self):
        """Test conversion from Ki to Gi."""
        assert format_memory("527554188Ki") == "503.1Gi"
        assert format_memory("1048576Ki") == "1Gi"
        assert format_memory("2097152Ki") == "2Gi"

    def test_mi_to_gi_conversion(self):
        """Test conversion from Mi to Gi."""
        assert format_memory("25047Mi") == "24.5Gi"
        assert format_memory("1024Mi") == "1Gi"
        assert format_memory("2048Mi") == "2Gi"

    def test_bytes_to_gi_conversion(self):
        """Test conversion from B to Gi."""
        assert format_memory("191655242229B") == "178.5Gi"
        assert format_memory("1073741824B") == "1Gi"

    def test_gi_unchanged(self):
        """Test that Gi values remain unchanged."""
        assert format_memory("100Gi") == "100Gi"
        assert format_memory("1.5Gi") == "1.5Gi"

    def test_ti_to_ti(self):
        """Test Ti values stay in Ti."""
        assert format_memory("1Ti") == "1Ti"
        assert format_memory("2.5Ti") == "2.5Ti"

    def test_decimal_stripping(self):
        """Test that .0 decimals are stripped."""
        assert format_memory("1048576Ki") == "1Gi"  # Not "1.0Gi"
        assert format_memory("1024Mi") == "1Gi"  # Not "1.0Gi"

    def test_decimal_preservation(self):
        """Test that non-zero decimals are preserved."""
        assert format_memory("25047Mi") == "24.5Gi"
        assert format_memory("1536Mi") == "1.5Gi"

    def test_invalid_format_unchanged(self):
        """Test that invalid formats are returned unchanged."""
        assert format_memory("invalid") == "invalid"
        assert format_memory("123") == "123"
        assert format_memory("") == ""
        assert format_memory("100 GB") == "100 GB"  # Space not supported

    def test_unknown_unit_unchanged(self):
        """Test that unknown units are returned unchanged."""
        assert format_memory("100GB") == "100GB"
        assert format_memory("100MB") == "100MB"
        assert format_memory("100kb") == "100kb"

    def test_small_values_to_mi(self):
        """Test small values convert to Mi."""
        assert format_memory("1024Ki") == "1Mi"
        assert format_memory("2048Ki") == "2Mi"

    def test_boundary_values(self):
        """Test boundary values for unit selection."""
        # Just under 1 Ki
        assert format_memory("1023B") == "1023B"
        # Exactly 1 Ki
        assert format_memory("1024B") == "1Ki"
        # Just under 1 Mi
        assert format_memory("1023Ki") == "1023Ki"
        # Exactly 1 Mi
        assert format_memory("1024Ki") == "1Mi"

    def test_whitespace_handling(self):
        """Test that spaces in input are handled correctly."""
        # No space is the standard format
        assert format_memory("1024Ki") == "1Mi"
        # With space is also supported (regex has \s*)
        assert format_memory("1024 Ki") == "1Mi"
        assert format_memory("2048  Mi") == "2Gi"


class TestFormatCpu:
    """Test format_cpu function."""

    def test_millicores_to_cores_conversion(self):
        """Test conversion from millicores to cores."""
        assert format_cpu("8000m") == "8 cores"
        assert format_cpu("7500m") == "7.5 cores"
        assert format_cpu("15500m") == "15.5 cores"
        assert format_cpu("1000m") == "1 cores"

    def test_cores_unchanged(self):
        """Test that core values remain unchanged."""
        assert format_cpu("8 cores") == "8 cores"
        assert format_cpu("16 cores") == "16 cores"
        assert format_cpu("1.5 cores") == "1.5 cores"

    def test_millicores_below_1000_unchanged(self):
        """Test that millicores below 1000 remain unchanged."""
        assert format_cpu("500m") == "500m"
        assert format_cpu("250m") == "250m"
        assert format_cpu("999m") == "999m"

    def test_decimal_stripping(self):
        """Test that .0 decimals are stripped."""
        assert format_cpu("8000m") == "8 cores"  # Not "8.0 cores"
        assert format_cpu("2000m") == "2 cores"  # Not "2.0 cores"

    def test_decimal_preservation(self):
        """Test that non-zero decimals are preserved."""
        assert format_cpu("7500m") == "7.5 cores"
        assert format_cpu("1500m") == "1.5 cores"
        assert format_cpu("2250m") == "2.2 cores"

    def test_invalid_format_unchanged(self):
        """Test that invalid formats are returned unchanged."""
        assert format_cpu("invalid") == "invalid"
        assert format_cpu("123") == "123"
        assert format_cpu("") == ""
        assert format_cpu("8 CPUs") == "8 CPUs"

    def test_unknown_unit_unchanged(self):
        """Test that unknown units are returned unchanged."""
        assert format_cpu("8vCPU") == "8vCPU"
        assert format_cpu("100MHz") == "100MHz"

    def test_whitespace_handling(self):
        """Test handling of whitespace in input."""
        # Standard format without space before 'm'
        assert format_cpu("8000m") == "8 cores"
        # With space is also supported (regex has \s*)
        assert format_cpu("8000 m") == "8 cores"
        assert format_cpu("1500  m") == "1.5 cores"

    def test_fractional_millicores(self):
        """Test fractional millicore values."""
        assert format_cpu("1250.5m") == "1.3 cores"
        assert format_cpu("3333.3m") == "3.3 cores"
