# Profiles System - Requirements and Design

## Overview

The Profiles system is a dependency management framework for organizing and selecting rule sets in the in-cluster-checks project. It provides hierarchical profile definitions with automatic transitive dependency resolution.

## Requirements

### Functional Requirements

1. **Hierarchical Profile Organization**
   - Support nested profile definitions with include relationships
   - Allow profiles to reference other profiles as dependencies
   - Resolve transitive dependencies automatically (flatten dependency tree)

2. **YAML Configuration**
   - Store profile definitions in a YAML file (`profiles.yaml`)
   - Support simple, readable configuration format
   - Allow profiles with no dependencies (leaf nodes)

3. **Dependency Resolution**
   - Automatically resolve all transitive dependencies at load time
   - Store resolved dependencies as flat sets for fast lookup
   - Support multiple levels of nesting (tested up to 3+ levels)

4. **Error Handling**
   - Detect and report circular dependencies
   - Detect and report undefined profile references
   - Provide helpful error messages with available options

5. **Global Singleton Access**
   - Provide a global `profile` object accessible throughout the codebase
   - Allow simple dictionary-like access to profile data
   - Support standard dict operations (keys, values, items, etc.)

### Non-Functional Requirements

1. **Performance**
   - Resolve dependencies once at load time (not on every access)
   - Use efficient set operations for dependency tracking
   - Fast lookups via dictionary structure

2. **Usability**
   - Simple, intuitive API
   - Clear error messages with context
   - Pretty-printed output for debugging

3. **Maintainability**
   - Clean separation of concerns (loader, profile, storage)
   - Well-tested with comprehensive unit tests
   - Clear documentation and examples

## Design

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    profiles.yaml                        │
│  - YAML configuration file                               │
│  - Defines profile hierarchy                            │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                 ProfileLoader                           │
│  - Reads YAML configuration                              │
│  - Resolves transitive dependencies                      │
│  - Detects circular dependencies                         │
│  - Populates global profile singleton                   │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    Profile                              │
│  - Inherits from dict[str, set[str]]                     │
│  - Global singleton instance                             │
│  - Stores flat, resolved dependencies                    │
│  - Provides helpful error messages                       │
│  - JSON-formatted string representation                  │
└─────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. **profiles.yaml** - Configuration File

Location: `src/profiles/profiles.yaml`

Structure:
```yaml
profiles:
  profile_name:
    include:
      - dependency1
      - dependency2

  leaf_profile: null  # No dependencies
```

Example:
```yaml
profiles:
  all:
    include: [telco, ai]

  general: null

  telco:
    include: [general, rh-nokia]

  rh-nokia:
    include: [general, telco-base]

  telco-base:
    include: [general]
```

#### 2. **Profile** Class - Data Container

File: `src/profiles/profile.py`

Key Features:
- Inherits from `dict[str, set[str]]`
- Global singleton instance: `profile`
- Enhanced `__getitem__()` with helpful error messages
- JSON-formatted `__str__()` representation
- Concise `__repr__()` for debugging

```python
class Profile(dict):
    """Maps profile names to their flat, resolved dependencies."""

    def __getitem__(self, key: str) -> set:
        """Get profile with helpful error if not found."""

    def format_profiles(self) -> str:
        """Return JSON-formatted representation."""
```

#### 3. **ProfileLoader** Class - Loading and Resolution

File: `src/profiles/loader.py`

Key Features:
- Static methods (no instance needed)
- Two-pass loading algorithm
- Recursive dependency resolution with cycle detection
- Populates global `profile` singleton

```python
class ProfileLoader:
    @staticmethod
    def load(config_path: str | None = None) -> None:
        """Load and resolve profile configuration."""

    @staticmethod
    def _resolve_and_populate(raw_profiles: dict) -> None:
        """Two-pass resolution: parse then resolve."""

    @staticmethod
    def _resolve_recursive(name, direct_includes, visiting, path) -> set:
        """Recursively resolve dependencies with cycle detection."""
```

### Loading Algorithm

**Two-Pass Resolution:**

1. **First Pass - Parse Direct Includes**
   ```python
   for name, config in yaml_data.items():
       direct_includes[name] = set(config.get("include", []))
   ```

2. **Second Pass - Resolve Transitive Dependencies**
   ```python
   for name in profiles:
       resolved = resolve_recursive(name)  # DFS traversal
       profile[name] = resolved           # Store flat set
   ```

**Recursive Resolution (DFS with Cycle Detection):**

```
function resolve_recursive(name, visiting, path):
    if name in visiting:
        raise ValueError("Circular dependency: " + path + name)

    visiting.add(name)
    resolved = set()

    for dependency in direct_includes[name]:
        resolved.add(dependency)
        sub_deps = resolve_recursive(dependency, visiting, path + [name])
        resolved.update(sub_deps)  # Flatten

    visiting.remove(name)
    return resolved
```

### Dependency Resolution Example

Given YAML:
```yaml
profiles:
  all: {include: [telco, ai]}
  telco: {include: [general, rh-nokia]}
  rh-nokia: {include: [general, telco-base]}
  telco-base: {include: [general]}
  general: null
  ai: {include: [general]}
```

Resolution for `all`:
```
Level 0: all
  ├─ includes: [telco, ai]
  │
  ├─ Level 1: telco
  │    ├─ includes: [general, rh-nokia]
  │    │
  │    └─ Level 2: rh-nokia
  │         ├─ includes: [general, telco-base]
  │         │
  │         └─ Level 3: telco-base
  │              └─ includes: [general]
  │
  └─ Level 1: ai
       └─ includes: [general]

Result: all = {telco, ai, general, rh-nokia, telco-base}
```

## Implementation Details

### File Structure

```
src/profiles/
├── __init__.py              # Empty (no exports)
├── profile.py              # Profile class + global singleton
├── loader.py                # ProfileLoader class
├── profiles.yaml           # Configuration file
└── example.py               # Usage examples
```

### Data Flow

```
1. ProfileLoader.load()
       ↓
2. Read profiles.yaml
       ↓
3. yaml.safe_load() → dict
       ↓
4. _resolve_and_populate()
       ↓
5. First pass: extract direct includes
       ↓
6. Second pass: resolve recursively
       ↓
7. Populate global profile singleton
       ↓
8. Ready for use: profile["profile_name"]
```

## Usage

### Basic Usage

```python
from profiles.loader import ProfileLoader
from profiles.profile import profile

# Load configuration
ProfileLoader.load()

# Access profile dependencies (flat, resolved)
nvidia_deps = profile["nvidia"]
# Returns: {'ai', 'ai-base', 'gpu', 'general'}

# Iterate over all profiles
for name, deps in profile.items():
    print(f"{name}: {deps}")

# Pretty print
print(profile)  # JSON-formatted output
```

### Error Handling

```python
# Non-existent profile
try:
    deps = profile["does_not_exist"]
except KeyError as e:
    print(e)
    # Output:
    # Profile 'does_not_exist' not found.
    #
    # Available profiles:
    # {
    #     "ai": ["ai-base", "general", "gpu"],
    #     "all": ["ai", "general", "telco", ...],
    #     ...
    # }
```

### Custom Configuration Path

```python
ProfileLoader.load("/path/to/custom/profiles.yaml")
```

## Testing

### Test Coverage

File: `tests/test_profiles.py`

**7 Test Cases:**

1. ✅ **test_all_contains_all_profiles**
   - Validates 'all' transitively includes every profile

2. ✅ **test_recursion_3_levels**
   - Tests 4 levels of dependency nesting
   - Path: all → telco → rh-nokia → telco-base → general

3. ✅ **test_non_existent_profile_raises_exception**
   - Verifies helpful KeyError messages

4. ✅ **test_circular_dependency_detection**
   - Ensures cycles are caught (a → b → c → a)

5. ✅ **test_missing_dependency_raises_exception**
   - Validates undefined reference detection

6. ✅ **test_empty_profile_has_no_dependencies**
   - Tests leaf nodes (profiles with no includes)

7. ✅ **test_transitive_dependencies_no_duplicates**
   - Ensures flat sets contain unique entries

### Running Tests

```bash
source .venv/bin/activate
pytest tests/test_profiles.py -v
```

## Design Decisions

### 1. **Global Singleton Pattern**

**Decision:** Use a global `profile` singleton instance.

**Rationale:**
- Single source of truth across the application
- Simple access pattern: `from profiles.profile import profile`
- No need to pass profile instance around
- Matches existing project patterns

**Alternative Considered:** Factory pattern with instance creation
- **Rejected:** More complex, unnecessary for this use case

### 2. **Flat Storage (Resolved at Load Time)**

**Decision:** Store fully resolved, flat dependency sets.

**Rationale:**
- Fast lookups: O(1) instead of O(n) traversal
- Resolve once, use many times
- Simpler client code
- Pre-validates all dependencies

**Alternative Considered:** Store direct includes, resolve on demand
- **Rejected:** Slower, requires traversal on every access

### 3. **Inherit from dict**

**Decision:** `Profile` inherits from `dict[str, set[str]]`.

**Rationale:**
- Familiar API (keys, values, items, in, len)
- Easy integration with existing code
- Can override specific methods (e.g., `__getitem__`)
- Still behaves like a dict

**Alternative Considered:** Composition (contain a dict)
- **Rejected:** More boilerplate, less intuitive

### 4. **JSON Format for String Representation**

**Decision:** Use `json.dumps(indent=4)` for `__str__()`.

**Rationale:**
- Clean, readable output
- Standard format
- Easy to parse if needed
- Proper indentation

**Alternative Considered:** Python repr format, pprint
- **Rejected:** JSON is more universal and cleaner

### 5. **Two-Pass Loading Algorithm**

**Decision:** Separate parsing from resolution.

**Rationale:**
- Clear separation of concerns
- Easier to test and debug
- Can validate structure before resolution
- Simpler error handling

**Alternative Considered:** Single-pass resolution
- **Rejected:** More complex, harder to detect errors early

## Future Enhancements

Potential improvements (not currently implemented):

1. **Profile Metadata**
   - Add descriptions, tags, or other metadata
   - Example: `{name: "ai", description: "AI workloads", include: [...]}`

2. **Rule Lists**
   - Associate actual rules with profiles
   - Example: `{name: "ai", include: [...], rules: ["check_gpu", ...]}`

3. **Validation**
   - Require 'all' profile to exist
   - Validate 'all' includes everything
   - Custom validation hooks

4. **Performance Optimization**
   - Cache resolved dependencies
   - Lazy loading for large configurations
   - Incremental resolution

5. **CLI Integration**
   - `--profile nvidia` to select profile
   - `--list-profiles` to show available options
   - Filter rules by profile selection

## Summary

The Profiles system provides a robust, well-tested framework for managing hierarchical rule dependencies. Key strengths:

- **Simple**: Easy YAML configuration, intuitive API
- **Fast**: O(1) lookups, pre-resolved dependencies
- **Robust**: Comprehensive error detection and helpful messages
- **Well-tested**: 7 unit tests covering all major scenarios
- **Maintainable**: Clean architecture, clear separation of concerns

The design successfully balances simplicity, performance, and maintainability while meeting all functional requirements.
