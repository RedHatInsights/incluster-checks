#!/usr/bin/env python3
"""
Pre-commit hook to prevent imports inside functions.

This script checks Python files for import statements inside function/method definitions.
Module-level try-except blocks for optional dependencies are allowed.
"""

import ast
import sys
from pathlib import Path


class FunctionImportChecker(ast.NodeVisitor):
    """AST visitor to find imports inside function definitions."""

    def __init__(self, filename: str, source_lines: list[str]):
        self.filename = filename
        self.source_lines = source_lines
        self.errors = []
        self.in_function = False
        self.in_try_except = False
        self.try_except_depth = 0

    def _has_noqa_comment(self, lineno: int) -> bool:
        """Check if the line has a noqa comment to suppress this check."""
        if lineno <= 0 or lineno > len(self.source_lines):
            return False
        line = self.source_lines[lineno - 1]
        # Support both general noqa and specific PLC0415 (Pylint code for import-outside-toplevel)
        return "# noqa" in line and ("PLC0415" in line or "function-import" in line)

    def visit_FunctionDef(self, node):
        """Visit function definition - track that we're inside a function."""
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definition - track that we're inside a function."""
        old_in_function = self.in_function
        self.in_function = True
        self.generic_visit(node)
        self.in_function = old_in_function

    def visit_Try(self, node):
        """Visit try-except block - track depth for module-level exception handling."""
        old_depth = self.try_except_depth
        self.try_except_depth += 1
        self.generic_visit(node)
        self.try_except_depth = old_depth

    def visit_Import(self, node):
        """Check if import is inside a function."""
        if self.in_function and not self._has_noqa_comment(node.lineno):
            # Import inside function is not allowed (unless noqa comment present)
            self.errors.append(
                f"{self.filename}:{node.lineno}: Import inside function/method is not allowed: "
                f"import {', '.join(alias.name for alias in node.names)}"
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Check if from-import is inside a function."""
        if self.in_function and not self._has_noqa_comment(node.lineno):
            # Import inside function is not allowed (unless noqa comment present)
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            self.errors.append(
                f"{self.filename}:{node.lineno}: Import inside function/method is not allowed: "
                f"from {module} import {names}"
            )
        self.generic_visit(node)


def check_file(filepath: Path) -> list:
    """
    Check a Python file for imports inside functions.

    Args:
        filepath: Path to Python file

    Returns:
        List of error messages (empty if no errors)
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        source_lines = source.splitlines()
        tree = ast.parse(source, filename=str(filepath))
        checker = FunctionImportChecker(str(filepath), source_lines)
        checker.visit(tree)
        return checker.errors

    except SyntaxError as e:
        return [f"{filepath}:{e.lineno}: Syntax error: {e.msg}"]
    except Exception as e:
        return [f"{filepath}: Failed to check file: {e}"]


def main():
    """Main entry point for pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: check_no_function_imports.py <file1.py> [file2.py ...]")
        sys.exit(0)

    all_errors = []
    for filepath in sys.argv[1:]:
        path = Path(filepath)
        if path.suffix == ".py":
            errors = check_file(path)
            all_errors.extend(errors)

    if all_errors:
        print("\n❌ Found imports inside functions:")
        print()
        for error in all_errors:
            print(f"  {error}")
        print()
        print("💡 Move all imports to the top of the file.")
        print()
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
