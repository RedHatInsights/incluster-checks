#!/usr/bin/env python3
"""
Pre-commit linter to enforce safe SafeCmdString usage.

This linter ensures SafeCmdString is only used with literal string templates to prevent
shell injection. Template arguments must be string literals, not variables, expressions,
or dynamically constructed strings.

SAFE patterns:
  SafeCmdString("literal command")                    # Static command
  SafeCmdString("find {path}").format(path="/tmp")    # Template with safe variables

UNSAFE patterns (detected and blocked):
  SafeCmdString(f"cmd {var}")                         # f-string - blocked
  SafeCmdString("echo " + var)                        # concatenation - blocked
  SafeCmdString(template_var)                         # variable - blocked
  SafeCmdString("cmd".format(var=x))                  # pre-formatted - blocked
  cmd1, cmd2 = SafeCmdString("a"), SafeCmdString("b") # multiple per line - blocked

Runtime protection:
  SafeCmdString.format() validates all variables to block dangerous shell metacharacters
  (semicolons, pipes, redirects, quotes, etc.) preventing injection at runtime.
"""

import ast
import sys
from pathlib import Path


class SafeCmdStringChecker(ast.NodeVisitor):
    """AST visitor to find unsafe SafeCmdString usage."""

    def __init__(self, filename: str):
        self.filename = filename
        self.errors = []
        self.current_class = None
        self.current_method = None
        self.calls_by_line = {}  # Track {line_number: [Call nodes]}
        self.parent_map = {}  # Track parent nodes for BinOp detection

    def visit_ClassDef(self, node):
        """Track current class."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """Track current method."""
        old_method = self.current_method
        self.current_method = node.name
        self.generic_visit(node)
        self.current_method = old_method

    def visit_Call(self, node):
        """Check all function calls for SafeCmdString usage."""
        # Check if this is a SafeCmdString() call
        if self._is_safe_cmd_string_call(node):
            # Track this call by line number
            lineno = node.lineno
            if lineno not in self.calls_by_line:
                self.calls_by_line[lineno] = []
            self.calls_by_line[lineno].append(node)

            # Skip validation if inside SafeCmdString internal methods (safe internal usage)
            if not (self.current_class == "SafeCmdString" and self.current_method in ("format", "__add__")):
                self._check_safe_cmd_string_arg(node)

        self.generic_visit(node)

    def _is_safe_cmd_string_call(self, node: ast.Call) -> bool:
        """Check if this call is SafeCmdString(...)."""
        if isinstance(node.func, ast.Name) and node.func.id == "SafeCmdString":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "SafeCmdString":
            return True
        return False

    def _check_safe_cmd_string_arg(self, node: ast.Call):
        """Check that SafeCmdString argument is a literal string only."""
        if not node.args:
            # No arguments - this is an error anyway (TypeError at runtime)
            return

        arg = node.args[0]

        # ONLY ALLOW: String literals (ast.Constant with str value)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            # This is safe - literal string
            return

        # Everything else is UNSAFE
        error_msg = f"{self.filename}:{node.lineno}: "

        if isinstance(arg, ast.JoinedStr):
            # f-string
            error_msg += "SafeCmdString() only accepts literal strings, not f-strings. "
        elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add):
            # String concatenation
            error_msg += "SafeCmdString() only accepts literal strings, not concatenated strings. "
        elif isinstance(arg, ast.Call):
            if isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
                # str.format()
                error_msg += "SafeCmdString() only accepts literal strings, not .format() results. "
            else:
                # Function call
                error_msg += "SafeCmdString() only accepts literal strings, not function call results. "
        elif isinstance(arg, ast.Name):
            # Variable
            error_msg += f"SafeCmdString() only accepts literal strings, not variables ('{arg.id}'). "
        elif isinstance(arg, ast.Attribute):
            # Attribute access (module.CONST)
            error_msg += "SafeCmdString() only accepts literal strings, not attribute access. "
        elif isinstance(arg, ast.Subscript):
            # Subscript (dict['key'] or list[0])
            error_msg += "SafeCmdString() only accepts literal strings, not subscript access. "
        else:
            # Unknown type
            error_msg += "SafeCmdString() only accepts literal strings. "

        error_msg += "Use SafeCmdString('template {var}').format(var=...) instead."
        self.errors.append(error_msg)

    def _all_calls_in_binop_chain(self, calls: list) -> bool:
        """Check if all calls are part of a BinOp addition chain."""
        for call in calls:
            if not self._is_part_of_binop_chain(call):
                return False
        return True

    def _is_part_of_binop_chain(self, node: ast.Call) -> bool:
        """Check if a Call node is part of a BinOp with Add operator."""
        current = node
        while current in self.parent_map:
            parent = self.parent_map[current]

            # Check if parent is BinOp with Add
            if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Add):
                # Verify both operands are SafeCmdString calls (or nested BinOps)
                if self._is_safe_cmd_string_or_binop(parent.left) and \
                   self._is_safe_cmd_string_or_binop(parent.right):
                    return True

            # Check if parent is another BinOp (for chained operations)
            if isinstance(parent, ast.BinOp):
                current = parent
                continue

            # If parent is Assign, Expr, etc., stop checking
            break

        return False

    def _is_safe_cmd_string_or_binop(self, node) -> bool:
        """Check if node is a SafeCmdString call or BinOp containing SafeCmdString calls."""
        # Check if it's a Call node and is SafeCmdString
        if isinstance(node, ast.Call) and self._is_safe_cmd_string_call(node):
            return True
        # Check if it's a BinOp with Add operator containing SafeCmdString calls
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return (self._is_safe_cmd_string_or_binop(node.left) and
                    self._is_safe_cmd_string_or_binop(node.right))
        return False


def check_file(filepath: Path) -> list:
    """
    Check a Python file for unsafe SafeCmdString usage.

    Args:
        filepath: Path to Python file

    Returns:
        List of error messages (empty if no errors)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        # Skip files that don't use SafeCmdString
        if "SafeCmdString" not in source:
            return []

        tree = ast.parse(source, filename=str(filepath))
        checker = SafeCmdStringChecker(str(filepath))

        # Build parent map for BinOp detection
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                checker.parent_map[child] = node

        checker.visit(tree)

        # Check for multiple calls per line (unless they're part of BinOp concatenation)
        for lineno, calls in checker.calls_by_line.items():
            if len(calls) > 1:
                # Check if all calls are part of BinOp addition chains
                if not checker._all_calls_in_binop_chain(calls):
                    checker.errors.append(
                        f"{filepath}:{lineno}: Multiple SafeCmdString() calls on same line detected. "
                        f"Found {len(calls)} calls. Split each call to a separate line to avoid validation ambiguity, "
                        f"or use the + operator to concatenate SafeCmdString objects."
                    )

        return checker.errors

    except SyntaxError as e:
        return [f"{filepath}:{e.lineno}: Syntax error: {e.msg}"]
    except Exception as e:
        return [f"{filepath}: Failed to check file: {e}"]


def main():
    """Main entry point for pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check_safe_cmd_string.py <file1.py> [file2.py ...]")
        sys.exit(0)

    all_errors = []
    for filepath in sys.argv[1:]:
        path = Path(filepath)
        if path.suffix == ".py":
            errors = check_file(path)
            all_errors.extend(errors)

    if all_errors:
        print("\nFound unsafe SafeCmdString usage:")
        print()
        for error in all_errors:
            print(f"  {error}")
        print()
        print("Use SafeCmdString('template {var}').format(var=...) for safe command formatting.")
        print("This validates variables to prevent shell injection.")
        print()
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
