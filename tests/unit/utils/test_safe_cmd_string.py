"""Tests for SafeCmdString."""

import pytest

from in_cluster_checks.utils.safe_cmd_string import SafeCmdString


def test_safe_cmd_string_static():
    """Test static command (no placeholders)."""
    cmd = SafeCmdString("cat /etc/hostname")
    assert str(cmd) == "cat /etc/hostname"


def test_safe_cmd_string_format_returns_safe_cmd_string():
    """Test that format() returns SafeCmdString."""
    cmd = SafeCmdString("echo {message}")
    result = cmd.format(message="hello")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo hello"


def test_safe_cmd_string_blocks_semicolon():
    """Test that semicolons are blocked."""
    cmd = SafeCmdString("find {path}")

    # Semicolons are blocked and should raise error
    with pytest.raises(ValueError) as exc_info:
        cmd.format(path="/tmp; rm -rf /")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert ";" in error_msg


def test_safe_cmd_string_multiple_vars():
    """Test multiple variables with safe characters."""
    cmd = SafeCmdString("command {arg1} {arg2} {arg3}")
    result = cmd.format(
        arg1="/path/to/file",
        arg2="/another/path",
        arg3="simple"
    )

    # All variables use only allowed characters (letters, numbers, spaces, /)
    result_str = str(result)
    assert result_str == "command /path/to/file /another/path simple"


def test_safe_cmd_string_format_no_kwargs_returns_self():
    """Test that format() with no kwargs returns self."""
    cmd = SafeCmdString("cat /etc/hostname")
    result = cmd.format()

    assert result is cmd


def test_safe_cmd_string_network_interface_names():
    """Test that network interface names with dashes and dots are allowed."""
    cmd = SafeCmdString("ip link show {iface}")

    # Interface names with dashes and dots should work
    result = cmd.format(iface="br-ex")
    assert str(result) == "ip link show br-ex"

    result = cmd.format(iface="bond0.110")
    assert str(result) == "ip link show bond0.110"

    result = cmd.format(iface="ovn-k8s-mp0")
    assert str(result) == "ip link show ovn-k8s-mp0"

    assert isinstance(result, SafeCmdString)


def test_safe_cmd_string_allows_spaces():
    """Test that spaces are allowed in identifiers."""
    cmd = SafeCmdString("echo {message}")

    # Spaces should work
    result = cmd.format(message="hello world")
    assert str(result) == "echo 'hello world'"

    # Test with positional placeholder
    cmd = SafeCmdString("echo {}")
    result = cmd.format("hello world")
    assert str(result) == "echo 'hello world'"

    assert isinstance(result, SafeCmdString)


def test_safe_cmd_string_blocks_leading_dash():
    """Test that leading dashes are blocked (security issue)."""
    cmd = SafeCmdString("rm {file}")

    # Leading dash could be interpreted as flag (-rf, --help, etc.)
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="-rf")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="--help")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()


def test_safe_cmd_string_blocks_leading_dot():
    """Test that leading dots are blocked (hidden files and path traversal)."""
    cmd = SafeCmdString("cat {file}")

    # Leading dot could access hidden files
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file=".hidden")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    # Double dot for parent directory traversal
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="..")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    # Path traversal attacks
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="../../../etc/passwd")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    # Hidden shell config files
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file=".bashrc")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    # Executing local scripts with ./
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="./script")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()


def test_safe_cmd_string_blocks_leading_space():
    """Test that leading spaces are blocked."""
    cmd = SafeCmdString("echo {value}")

    # Leading space could cause parsing issues
    with pytest.raises(ValueError) as exc_info:
        cmd.format(value=" test")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()

    # Multiple leading spaces
    with pytest.raises(ValueError) as exc_info:
        cmd.format(value="  test")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()


def test_safe_cmd_string_empty_value():
    """Test that empty values are handled."""
    cmd = SafeCmdString("cmd {arg}")
    result = cmd.format(arg="")

    result_str = str(result)
    # Empty string is inserted as-is (no quoting needed)
    assert result_str == "cmd "


@pytest.mark.parametrize(
    "blocked_char,test_value",
    [
        (";", "test;rm"),
        ("|", "test|cat"),
        ("&", "test&"),
        ("$", "test$VAR"),
        ("`", "test`cmd`"),
        ("<", "test<file"),
        (">", "test>file"),
        ("\\", "test\\escape"),
    ],
)
def test_safe_cmd_string_blocks_dangerous_characters(blocked_char, test_value):
    """Test that blocked dangerous shell metacharacters raise errors."""
    cmd = SafeCmdString("echo {value}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format(value=test_value)

    error_msg = str(exc_info.value)
    expected_msg = (
        f"Parameter 'value' contains invalid characters.\n"
        f"Allowed patterns:\n"
        f"  - Absolute paths: /path/to/file or /path/to/file.ext\n"
        f"    (letters, digits, dashes, underscores; ONE dot in filename only)\n"
        f"  - Identifiers: alphanumeric start, then letters/digits/dots/dashes/spaces\n"
        f"    (e.g., 'eth0', 'br-ex', 'bond0.110', 'ovn-k8s-mp0')\n"
        f"  - Etcd URLs: https://etcd-N.etcd.openshift-etcd.svc:2379/path\n"
        f"  - PCI addresses: 01:00.0 or 0000:01:00.0\n"
        f"Got: {test_value!r}"
    )
    assert error_msg == expected_msg


@pytest.mark.parametrize(
    "special_char,test_value",
    [
        ('"', 'test"quoted'),
        ("'", "test'quoted"),
        ("{", "test{brace"),
        ("}", "test}brace"),
        ("!", "test!"),
        ("\t", "test\tvalue"),
        ("\n", "test\nvalue"),
        ("#", "test#comment"),
        ("=", "test=value"),
        ("_", "test_file"),  # Underscore not allowed (not used in actual code)
        (":", "test:value"),
        ("@", "test@host"),
        ("*", "test*.log"),
        ("?", "test?.txt"),
        ("[", "test[0]"),
        ("]", "test[0]"),
    ],
)
def test_safe_cmd_string_blocks_invalid_characters(special_char, test_value):
    """Test that invalid characters (not letters/numbers/dots/dashes/spaces/slash) are blocked."""
    cmd = SafeCmdString("echo {value}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format(value=test_value)

    error_msg = str(exc_info.value)
    expected_msg = (
        f"Parameter 'value' contains invalid characters.\n"
        f"Allowed patterns:\n"
        f"  - Absolute paths: /path/to/file or /path/to/file.ext\n"
        f"    (letters, digits, dashes, underscores; ONE dot in filename only)\n"
        f"  - Identifiers: alphanumeric start, then letters/digits/dots/dashes/spaces\n"
        f"    (e.g., 'eth0', 'br-ex', 'bond0.110', 'ovn-k8s-mp0')\n"
        f"  - Etcd URLs: https://etcd-N.etcd.openshift-etcd.svc:2379/path\n"
        f"  - PCI addresses: 01:00.0 or 0000:01:00.0\n"
        f"Got: {test_value!r}"
    )
    assert error_msg == expected_msg


def test_safe_cmd_string_repr():
    """Test repr output."""
    cmd = SafeCmdString("test command")
    assert repr(cmd) == "SafeCmdString('test command')"


def test_safe_cmd_string_pipeline():
    """Test command with pipe (literal, not placeholder)."""
    # Pipe is part of static command, not a placeholder
    cmd = SafeCmdString("cat /proc/meminfo | grep HugePages")
    assert str(cmd) == "cat /proc/meminfo | grep HugePages"


def test_safe_cmd_string_with_env_vars():
    """Test command with environment variables (not placeholders)."""
    # $VAR is part of static command, will be expanded by shell
    cmd = SafeCmdString("echo $PATH {value}")
    result = cmd.format(value="test")

    result_str = str(result)
    assert "$PATH" in result_str  # Env var preserved
    assert "test" in result_str  # Value inserted


def test_runtime_internal_format_call_allowed():
    """Internal calls from format() should be allowed."""
    # This should not raise - format() internally creates SafeCmdString
    cmd = SafeCmdString("echo {msg}")
    result = cmd.format(msg="test")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo test"


def test_runtime_multiline_literal_allowed():
    """Multiline literal strings should be allowed."""
    cmd = SafeCmdString(
        "cat /etc/hostname"
    )
    assert str(cmd) == "cat /etc/hostname"


def test_runtime_injection_blocked():
    """Injection attempts should be blocked."""
    cmd = SafeCmdString("cat {file}")

    # Dangerous characters like semicolon are blocked
    with pytest.raises(ValueError) as exc_info:
        cmd.format(file="; rm -rf /")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert ";" in error_msg


def test_safe_cmd_string_allowed_paths():
    """Test that paths with only allowed characters work."""
    cmd = SafeCmdString("ls {path}")
    result = cmd.format(path="/var/log/messages")

    result_str = str(result)
    assert result_str == "ls /var/log/messages"


def test_safe_cmd_string_composition():
    """Test that SafeCmdString can be composed with other SafeCmdStrings."""
    # Create inner command
    inner_cmd = SafeCmdString("ceph health")

    # Compose with outer command
    result = SafeCmdString("{cmd} {path}").format(
        cmd=inner_cmd,
        path="/var/lib/config"
    )

    result_str = str(result)
    assert result_str == "ceph health /var/lib/config"
    assert isinstance(result, SafeCmdString)


def test_safe_cmd_string_composition_mixed():
    """Test composition with both SafeCmdString and regular parameters."""
    base_cmd = SafeCmdString("echo {message}")
    formatted_cmd = base_cmd.format(message="hello")

    # Compose formatted command with additional args
    result = SafeCmdString("{cmd} {path}").format(
        cmd=formatted_cmd,
        path="/tmp/output"
    )

    result_str = str(result)
    assert result_str == "echo hello /tmp/output"


# ============================================================================
# Positional Placeholder Tests
# ============================================================================


def test_safe_cmd_string_positional_single():
    """Test single positional placeholder."""
    cmd = SafeCmdString("sudo ethtool {}")
    result = cmd.format("eth0")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "sudo ethtool eth0"


def test_safe_cmd_string_positional_multiple():
    """Test multiple positional placeholders."""
    cmd = SafeCmdString("command {} {} {}")
    result = cmd.format("/path/one", "/path/two", "value")

    result_str = str(result)
    assert result_str == "command /path/one /path/two value"


def test_safe_cmd_string_positional_empty_value():
    """Test positional placeholder with empty string."""
    cmd = SafeCmdString("cmd {}")
    result = cmd.format("")

    result_str = str(result)
    assert result_str == "cmd "


def test_safe_cmd_string_positional_dangerous_char_blocked():
    """Test that blocked characters in positional args raise error."""
    cmd = SafeCmdString("cat {}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("/tmp; rm -rf /")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert ";" in error_msg


@pytest.mark.parametrize(
    "blocked_char,test_value",
    [
        (";", "test;rm"),
        ("|", "test|cat"),
        ("&", "test&"),
        ("$", "test$VAR"),
        ("`", "test`cmd`"),
        ("<", "test<file"),
        (">", "test>file"),
        ("\\", "test\\escape"),
    ],
)
def test_safe_cmd_string_positional_blocks_dangerous_characters(blocked_char, test_value):
    """Test that blocked dangerous shell metacharacters raise errors in positional args."""
    cmd = SafeCmdString("echo {}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format(test_value)

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert blocked_char in error_msg or repr(blocked_char) in error_msg


@pytest.mark.parametrize(
    "special_char,test_value",
    [
        ('"', 'test"quoted'),
        ("'", "test'quoted"),
        ("{", "test{brace"),
        ("}", "test}brace"),
        ("!", "test!"),
        ("\t", "test\tvalue"),
        ("\n", "test\nvalue"),
        ("#", "test#comment"),
        ("=", "test=value"),
        ("_", "test_file"),  # Underscore not allowed
        ("*", "test*.log"),
    ],
)
def test_safe_cmd_string_positional_blocks_invalid_characters(special_char, test_value):
    """Test that invalid characters are blocked in positional args."""
    cmd = SafeCmdString("echo {}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format(test_value)

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()


def test_safe_cmd_string_positional_composition():
    """Test composition with SafeCmdString as positional argument."""
    inner_cmd = SafeCmdString("ceph health")

    result = SafeCmdString("{} {}").format(
        inner_cmd,
        "/var/lib/config"
    )

    result_str = str(result)
    assert result_str == "ceph health /var/lib/config"
    assert isinstance(result, SafeCmdString)


# ============================================================================
# Mixed Positional and Named Placeholder Tests
# ============================================================================


def test_safe_cmd_string_mixed_positional_and_named():
    """Test mixing positional and named placeholders."""
    cmd = SafeCmdString("{} {port}")
    result = cmd.format("ethtool", port="eth0")

    assert isinstance(result, SafeCmdString)
    assert str(result) == "ethtool eth0"


def test_safe_cmd_string_mixed_multiple_positional_and_named():
    """Test multiple positional and named placeholders together."""
    cmd = SafeCmdString("{} {} {path} {pattern}")
    result = cmd.format("command", "grep", path="/var/log", pattern="error")

    result_str = str(result)
    assert result_str == "command grep /var/log error"


def test_safe_cmd_string_mixed_blocked_char_in_positional():
    """Test blocked character validation in mixed mode (positional arg)."""
    cmd = SafeCmdString("{} {name}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("test; rm", name="safe")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert ";" in error_msg


def test_safe_cmd_string_mixed_blocked_char_in_named():
    """Test blocked character validation in mixed mode (named arg)."""
    cmd = SafeCmdString("{} {name}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("safe", name="test; rm")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()
    assert ";" in error_msg


def test_safe_cmd_string_mixed_interface_names():
    """Test that interface names work in mixed mode."""
    cmd = SafeCmdString("{} {name}")

    result = cmd.format("ip", name="br-ex")

    result_str = str(result)
    assert "ip" in result_str
    assert "br-ex" in result_str
    assert isinstance(result, SafeCmdString)


def test_safe_cmd_string_mixed_leading_dash_blocked():
    """Test that leading dashes are blocked in mixed mode."""
    cmd = SafeCmdString("{} {name}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("safe", name="-rf")

    error_msg = str(exc_info.value)
    assert "invalid characters" in error_msg.lower()


def test_safe_cmd_string_mixed_composition():
    """Test composition with both positional and named in mixed mode."""
    base_cmd = SafeCmdString("echo {}")
    formatted_cmd = base_cmd.format("hello")

    result = SafeCmdString("{cmd} {output}").format(cmd=formatted_cmd, output="/tmp/out")

    result_str = str(result)
    assert result_str == "echo hello /tmp/out"


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


def test_safe_cmd_string_backward_compatibility_named_only():
    """Test that existing named-only usage still works with allowed characters."""
    cmd = SafeCmdString("command {arg1} {arg2} {arg3}")
    result = cmd.format(
        arg1="/path/one",
        arg2="/path/two",
        arg3="value"
    )

    result_str = str(result)
    assert result_str == "command /path/one /path/two value"


def test_safe_cmd_string_backward_compatibility_no_args():
    """Test that format() with no args still returns self."""
    cmd = SafeCmdString("cat /etc/hostname")
    result = cmd.format()

    assert result is cmd


# ============================================================================
# Addition Operator Tests
# ============================================================================


def test_safe_cmd_string_add_operator():
    """Test + operator for concatenation."""
    cmd1 = SafeCmdString("echo hello")
    cmd2 = SafeCmdString("echo world")

    result = cmd1 + cmd2

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo hello echo world"


def test_safe_cmd_string_add_chained():
    """Test chained + operations."""
    cmd1 = SafeCmdString("echo a")
    cmd2 = SafeCmdString("echo b")
    cmd3 = SafeCmdString("echo c")

    result = cmd1 + cmd2 + cmd3

    assert isinstance(result, SafeCmdString)
    assert str(result) == "echo a echo b echo c"


def test_safe_cmd_string_add_with_templates():
    """Test + operator with formatted commands."""
    cmd1 = SafeCmdString("find {path}").format(path="/tmp")
    cmd2 = SafeCmdString("grep {pattern}").format(pattern="test")

    result = cmd1 + cmd2

    assert isinstance(result, SafeCmdString)
    assert str(result) == "find /tmp grep test"


def test_safe_cmd_string_add_type_error():
    """Test that + operator rejects non-SafeCmdString operands."""
    cmd = SafeCmdString("echo hello")

    with pytest.raises(TypeError) as exc_info:
        cmd + "echo world"

    error_msg = str(exc_info.value)
    assert "unsupported operand type(s) for +" in error_msg
    assert "SafeCmdString" in error_msg
    assert "str" in error_msg


def test_safe_cmd_string_radd_type_error():
    """Test that reverse + also rejects non-SafeCmdString operands."""
    cmd = SafeCmdString("echo world")

    # This will fail because str.__add__ doesn't know about SafeCmdString
    # The result should be TypeError
    with pytest.raises(TypeError):
        "echo hello" + cmd


# ============================================================================
# Unfilled Placeholder Tests
# ============================================================================


def test_safe_cmd_string_unfilled_placeholder_named():
    """Test that unfilled named placeholders are detected."""
    cmd = SafeCmdString("{aaa}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format()

    error_msg = str(exc_info.value)
    assert "template has unfilled placeholders" in error_msg.lower()
    assert "{aaa}" in error_msg
    assert "you provided: no arguments" in error_msg.lower()
    assert "fix:" in error_msg.lower()
    assert ".format(aaa=...)" in error_msg.lower()


def test_safe_cmd_string_unfilled_placeholder_positional():
    """Test that unfilled positional placeholders are detected."""
    cmd = SafeCmdString("{}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format()

    error_msg = str(exc_info.value)
    assert "template has unfilled placeholders" in error_msg.lower()
    assert "{}" in error_msg
    assert "you provided: no arguments" in error_msg.lower()
    assert "fix:" in error_msg.lower()
    assert ".format(...)" in error_msg  # Should suggest positional format, not named


def test_safe_cmd_string_unfilled_multiple_placeholders():
    """Test that multiple unfilled placeholders are detected."""
    cmd = SafeCmdString("cmd {arg1} {arg2}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format()

    error_msg = str(exc_info.value)
    assert "template has unfilled placeholders" in error_msg.lower()
    assert "{arg1}" in error_msg
    assert "{arg2}" in error_msg
    assert "you provided: no arguments" in error_msg.lower()
    assert "fix:" in error_msg.lower()


# ============================================================================
# Template Mismatch Error Message Tests
# ============================================================================


def test_safe_cmd_string_named_placeholder_with_positional_arg():
    """Test clear error message when named placeholder gets positional argument."""
    cmd = SafeCmdString("{aaa}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("pwd")

    error_msg = str(exc_info.value)
    assert "template mismatch" in error_msg.lower()
    assert "{aaa}" in error_msg
    assert "expects a named argument" in error_msg.lower()
    assert ".format(aaa=...)" in error_msg


def test_safe_cmd_string_multiple_named_with_positional():
    """Test error message when multiple named placeholders get positional args."""
    cmd = SafeCmdString("cmd {arg1} {arg2}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("value1", "value2")

    error_msg = str(exc_info.value)
    assert "template mismatch" in error_msg.lower()
    assert "expects a named argument" in error_msg.lower()
    # Should mention one of the missing placeholders
    assert "{arg1}" in error_msg or "{arg2}" in error_msg


def test_safe_cmd_string_not_enough_positional_args():
    """Test clear error message when not enough positional arguments provided."""
    cmd = SafeCmdString("{} {} {}")

    with pytest.raises(ValueError) as exc_info:
        cmd.format("arg1", "arg2")  # Missing third argument

    error_msg = str(exc_info.value)
    assert "template mismatch" in error_msg.lower()
    assert "not enough positional arguments" in error_msg.lower()
    assert "2 positional args" in error_msg  # Shows what was provided


def test_safe_cmd_string_mixed_mismatch():
    """Test error message when mixing named and positional incorrectly."""
    cmd = SafeCmdString("{named1} {named2}")

    with pytest.raises(ValueError) as exc_info:
        # Providing positional instead of named
        cmd.format("value1", "value2")

    error_msg = str(exc_info.value)
    assert "template mismatch" in error_msg.lower()
    assert "expects a named argument" in error_msg.lower()
