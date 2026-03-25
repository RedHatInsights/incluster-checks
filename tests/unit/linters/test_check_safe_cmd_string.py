#!/usr/bin/env python3
"""Tests for SafeCmdString linter."""

import sys
import tempfile
from pathlib import Path

import pytest

# Add tests/linters to path so we can import the linter module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "linters"))

from check_safe_cmd_string import check_file


def test_linter_multiple_calls_same_line():
    """Test that linter detects multiple SafeCmdString calls on same line."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    cmd1, cmd2 = SafeCmdString("echo test1"), SafeCmdString("echo test2")
    return cmd1, cmd2
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have exactly one error about multiple calls
        assert len(errors) == 1
        error_msg = errors[0]
        assert "Multiple SafeCmdString() calls on same line" in error_msg
        assert "Found 2 calls" in error_msg
        assert "Split each call to a separate line" in error_msg
    finally:
        filepath.unlink()


def test_linter_single_call_per_line_allowed():
    """Test that single call per line is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    cmd1 = SafeCmdString("echo test1")
    cmd2 = SafeCmdString("echo test2")
    return cmd1, cmd2
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_multiline_call_allowed():
    """Test that multiline single call is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    cmd = SafeCmdString(
        "echo test"
    )
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_triple_calls_same_line():
    """Test that linter detects three calls on same line."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    a, b, c = SafeCmdString("cmd1"), SafeCmdString("cmd2"), SafeCmdString("cmd3")
    return a, b, c
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should detect 3 calls on same line
        assert len(errors) == 1
        assert "Found 3 calls" in errors[0]
    finally:
        filepath.unlink()


def test_linter_nested_safecmdstring_same_line():
    """Test that linter detects nested SafeCmdString on same line."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    cmd = SafeCmdString("{t}").format(t=SafeCmdString("nested"))
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should detect 2 calls on same line
        assert len(errors) == 1
        assert "Found 2 calls" in errors[0]
    finally:
        filepath.unlink()


def test_linter_nested_safecmdstring_separate_lines_allowed():
    """Test that nested SafeCmdString on separate lines is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    inner = SafeCmdString("nested")
    cmd = SafeCmdString("{t}").format(t=inner)
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_conditional_expression_separate_lines():
    """Test that conditional expression with calls on different lines is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func(condition):
    cmd = (SafeCmdString("cmd1") if condition else
           SafeCmdString("cmd2"))
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors - calls on different lines
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_still_catches_variables():
    """Test that linter still catches variable usage (existing check)."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    template = "echo test"
    cmd = SafeCmdString(template)
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have error about variable usage
        assert len(errors) == 1
        assert "not variables" in errors[0]
    finally:
        filepath.unlink()


def test_linter_still_catches_fstrings():
    """Test that linter still catches f-string usage (existing check)."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    value = "test"
    cmd = SafeCmdString(f"echo {value}")
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have error about f-string usage
        assert len(errors) == 1
        assert "not f-strings" in errors[0]
    finally:
        filepath.unlink()


def test_linter_catches_concatenation():
    """Test that linter catches string concatenation (existing check)."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    var = "test"
    cmd = SafeCmdString("echo " + var + " done")
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have error about concatenation
        assert len(errors) == 1
        assert "not concatenated strings" in errors[0]
    finally:
        filepath.unlink()


def test_linter_catches_preformatted():
    """Test that linter catches pre-formatted strings (format before SafeCmdString)."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    file = "/etc/passwd"
    cmd = SafeCmdString("cat {f}".format(f=file))
    return cmd
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have error about pre-formatted string
        assert len(errors) == 1
        assert "not .format() results" in errors[0]
    finally:
        filepath.unlink()


def test_linter_allows_binop_concatenation():
    """Test that + operator concatenation is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    result = SafeCmdString("cmd1") + SafeCmdString("cmd2")
    return result
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_allows_chained_concatenation():
    """Test that chained + operations are allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    result = SafeCmdString("a") + SafeCmdString("b") + SafeCmdString("c")
    return result
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_allows_multiline_concatenation():
    """Test that multiline + concatenation is allowed."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    result = (SafeCmdString("cmd1") +
              SafeCmdString("cmd2") +
              SafeCmdString("cmd3"))
    return result
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should have no errors (different lines)
        assert len(errors) == 0
    finally:
        filepath.unlink()


def test_linter_still_blocks_tuple_unpacking():
    """Test that tuple unpacking is still blocked (not BinOp)."""
    code = '''
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

def test_func():
    cmd1, cmd2 = SafeCmdString("a"), SafeCmdString("b")
    return cmd1, cmd2
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f.flush()
        filepath = Path(f.name)

    try:
        errors = check_file(filepath)

        # Should still error on tuple unpacking
        assert len(errors) == 1
        assert "Multiple SafeCmdString() calls on same line" in errors[0]
    finally:
        filepath.unlink()
