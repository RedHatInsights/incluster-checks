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

## Writing Rules from RCA or Command Output

**Extract the logic, not specific values from examples.**

When creating rules from RCA (Root Cause Analysis) or command output examples, understand the underlying pattern rather than copying specific values.

### Understand Actual Behavior, Not the Example

**Bad - Hardcoded from one example:**
```python
def get_external_bridge(self):
    return "br-ex"  # From RCA showing one specific cluster
```

**Good - Detect actual behavior:**
```python
def get_external_bridges(self):
    """Get all external bridges (those with physical ports)."""
    # Query OVS state and detect which bridges have physical ports
    # Returns dict, not hardcoded string
```

**Reasoning:** RCA examples show one specific case (br-ex). Real clusters may have different bridge names. Detect actual behavior instead of assuming.

### Verify Hardware Presence, Don't Assume

**Bad - Assume from naming pattern:**
```python
def is_physical_port(self, port):
    return port.startswith("bond") or port.startswith("eth")
```

**Good - Check actual hardware:**
```python
def is_hardware_backed(self, interface):
    # Check /sys/class/net/{interface}/device for physical NICs
    # Check /sys/class/net/{interface}/bonding/ for bonds
    # Returns True only if hardware actually exists
```

**Reasoning:** Interface names vary across clusters (ens3, enp1s0, eth0, bond0). Check actual hardware presence instead of name patterns.

### Handle Multiple Cases, Not Just the RCA Example

**Bad - Assume single instance:**
```python
def validate_vlans(self, vlans):
    bridge = self.get_external_bridge()  # Returns one bridge
    ports = self.get_bridge_ports(bridge)
```

**Good - Handle multiple instances:**
```python
def validate_vlans(self, vlans):
    bridges = self.get_external_bridges()  # Returns dict of all bridges
    all_ports = []
    for bridge_info in bridges.values():
        all_ports.extend(bridge_info["all_ports"])
```

**Reasoning:** RCA may show single bridge, but production clusters can have multiple bridges (br-ex, br-vm, etc.). Don't limit validation to one instance.

## Helper Functions Over Tuples

**Use separate helper functions instead of tuples for multiple return values.**

```python
# Bad - tuple return
def check_status(self) -> tuple[bool, bool]:
    return (command_ok, has_resource)

# Good - separate helpers
def is_command_accessible(self) -> bool:
    return self._run_check_command() == 0

def has_resource(self) -> bool:
    return self._find_resource() is not None
```

**When tuples are OK:**
- Tightly coupled values: `(success: bool, error_msg: str)`
- Standard patterns: `run_cmd()` returns `(rc, out, err)`
