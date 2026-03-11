# Code Style

## Code Style Guidelines

- **Line length**: 120 characters
- **Docstrings**: Use Google-style docstrings
- **Type hints**: Use type hints where appropriate (Python 3.12+)
- **Naming**:
  - Classes: `PascalCase`
  - Functions/methods: `snake_case`
  - Constants: `UPPER_CASE`
  - Private: prefix with `_`

## Import Organization

**ALWAYS place all imports at the top of the file** - never add imports in the middle of functions or methods.

Follow PEP 8 import order:
1. Standard library imports
2. Related third-party imports
3. Local application/library specific imports

Group imports with blank lines between categories.

**Example:**
```python
# Standard library
import os
from typing import Dict, List

# Third-party
import pytest

# Local application
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.utils.enums import Status
```

## Comments

**Only add comments when the code is hard to understand without them.**

- Don't add comments that restate what the code does
- Don't add comments for self-explanatory code or obvious operations
- Only add comments to explain complex algorithms, non-obvious workarounds, or important design decisions that aren't clear from the code itself

**Examples of unnecessary comments (avoid these):**
```python
self._threadLock = threading.Lock()  # Prevent parallel command execution

with self._threadLock:  # Use lock

self.node_name = node_name  # Set node name
```

## Conditional Checks

**Avoid redundant None checks when checking truthiness.**

When a variable can be None or empty (empty list, empty string, etc.), use `if not variable` instead of `if variable is None or not variable`.

**Examples:**

```python
# Good - concise and Pythonic
if not zone_type_lines:
    zone_type = "unknown"

# Bad - redundant check (if it's None, "not zone_type_lines" already catches it)
if zone_type_lines is None or not zone_type_lines:
    zone_type = "unknown"
```

**Reasoning:** In Python, `not variable` evaluates to `True` for:
- `None`
- Empty list `[]`
- Empty string `""`
- Empty dict `{}`
- `0`, `False`

So checking `is None` separately is redundant unless you specifically need to distinguish between `None` and empty collections.

## DRY Principle: Avoid Code Duplication

**NEVER duplicate logic across multiple files or functions.** Follow the DRY (Don't Repeat Yourself) principle.

When you find the same or very similar code in multiple places:
1. Identify the common logic
2. Extract it to a single location
3. Have all callers use the shared implementation

**Benefits:**
- Changes to logic only need to be made in one place
- Consistent behavior across all code paths
- Easier to test and maintain
- Better separation of concerns
