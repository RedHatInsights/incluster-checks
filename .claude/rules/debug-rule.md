# Debug Rule Flag

## Debug Logging Pattern

**Use the standardized `_debug_log()` helper for debug output when `--debug-rule` is active.**

The framework provides a consistent debug logging pattern in `OcApiUtils` that:
- Only prints when `global_config.debug_rule_flag` is True (set via `--debug-rule` CLI flag)
- Formats output as pretty JSON with fields equivalent to `oc get <resource> -o wide`
- Provides consistent `[DEBUG]` prefixed output across the codebase

## OcApiUtils Debug Logging

All `OcApiUtils` methods use the `_debug_log()` helper for consistent debug output:

```python
def select_resources(self, resource_type: str, ...) -> list:
    cmd_str = " ".join(cmd_parts)
    self.operator._add_cmd_to_log(cmd_str)
    
    # Print command before execution
    self._debug_log(f"Executing: {cmd_str}")
    
    # ... execute command ...
    
    # Print results after execution with JSON formatting
    base_type = resource_type.split("/")[-1].split(".")[0]
    self._debug_log(f"Found {len(result)} {base_type}(s)", obj=result, resource_type=base_type)
    
    return result
```

## Debug Output Format

The `_debug_log()` method:
1. Prints a debug message with `[DEBUG]` prefix
2. Optionally formats resource objects as pretty JSON
3. Shows only relevant fields (equivalent to `-o wide` output):
   - **Pods**: namespace, name, ready, status, restarts, age, ip, node
   - **Deployments**: namespace, name, ready, up-to-date, available, age
   - **Nodes**: name, status, roles, age, version
   - **Namespaces**: name, status, age
   - **DaemonSets**: namespace, name, desired, current, ready, up-to-date, available, age

**Example output:**
```
[DEBUG] Executing: oc get deployment -A

[DEBUG] Found 136 deployment(s)
[
  {
    "namespace": "assisted-chat",
    "name": "assisted-chat",
    "ready": "0/1",
    "up-to-date": 1,
    "available": 0,
    "age": "2024-11-15T10:30:00Z"
  },
  {
    "namespace": "assisted-chat",
    "name": "assisted-service-mcp",
    "ready": "0/1",
    "up-to-date": 1,
    "available": 0,
    "age": "2024-12-28T14:20:00Z"
  }
]
============================================================
```

## When to Use Debug Logging

**Use `_debug_log()` instead of `if global_config.debug_rule_flag: print()`:**
- ✅ In `OcApiUtils` methods that execute oc commands or query resources
- ✅ When showing command execution details (command string, result counts, etc.)
- ✅ When you need structured JSON output of resource objects

**Avoid debug logging:**
- ❌ Don't duplicate existing `logger.info()` or `logger.error()` calls
- ❌ Don't add debug logging if the information is already logged elsewhere
- ❌ Don't use in rules (rules should use `RuleResult` messages instead)

## Benefits

- **Consistency**: All debug output uses the same format
- **DRY**: Single method to update debug behavior across the codebase  
- **Readability**: Pretty JSON format instead of object repr strings
- **Maintainability**: Easy to enhance debug output in one place
