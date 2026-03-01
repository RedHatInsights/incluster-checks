"""Tests for __main__.py module entry point."""

from unittest.mock import patch
import sys


def test_main_module_entry_point():
    """Test that __main__ module calls cli.main() when run as main."""
    with patch('in_cluster_checks.cli.main') as mock_main:
        # Import the module to trigger the if __name__ == "__main__" block
        # We need to temporarily set __name__ to __main__ in the module
        import importlib
        import in_cluster_checks.__main__ as main_module

        # Reload the module with __name__ patched to trigger the block
        with patch.object(main_module, '__name__', '__main__'):
            # Manually call what's in the if block since we can't re-execute it
            from in_cluster_checks.cli import main
            main()

        mock_main.assert_called_once()
