# Contributing to OpenShift In-Cluster Checks

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Adding New Rules](#adding-new-rules)
- [Adding New Domains](#adding-new-domains)
- [Testing](#testing)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)

<!-- can be deleted -->
## Code of Conduct

This project follows a code of conduct. By participating, you are expected to uphold this code. Please be respectful and professional in all interactions.

## Getting Started

1. **Fork the repository** on GitHub <!-- do we want to give gitlab url? --> 
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/in-cluster-checks.git
   cd in-cluster-checks
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/sprizend-rh/in-cluster-checks.git
   ```

## Development Setup

1. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install development dependencies**:
    <!-- what is ".[dev]"? will it install requirements as Python >= 3.12? -->
   ```bash
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

4. **Verify setup**:
   ```bash
   pytest
   pre-commit run --all-files
   ```

## Making Code Changes

1. **Create a new branch**:
   ```bash
   git checkout -b YOUR-FEATURE-NAME
   ```

2. **Make your changes** following the code style guidelines

3. **Test your changes**:
    <!-- do we want to add proceedure how to test the code on env'? -->
   ```bash
   pytest
   pre-commit run --all-files
   ```

4. **Commit your changes**:
    <!-- should commit be related to JIRA ticket which can be more informative about the contribution? -->
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

   <!-- we should mention 'git pull' command and also 'git push' -->

## Understanding the Rules Hierarchy

The in-cluster-checks framework is organized into a three-level hierarchy:

### 1. **Rules** (Bottom Level)
Individual validation checks that run on cluster nodes. Each rule:
- Inherits from the `Rule` base class
- Executes specific commands via `oc debug`
- Returns pass/fail results with diagnostic information
- Targets specific node types (masters, workers, or all nodes)

**Location:** `src/in_cluster_checks/rules/<domain>/`

**Example:** `CheckDiskUsage`, `CheckNetworkConnectivity`, `CheckKernelVersion`

### 2. **Domains** (Middle Level)
Logical groupings of related rules. Each domain:
- Inherits from the `RuleDomain` base class
- Contains thematically related rules (e.g., hardware, network, storage)
- Returns a list of rule classes to execute

**Location:** `src/in_cluster_checks/domains/`

**Example Domains:**
- `hw` - Hardware validation rules (disk, CPU, memory)
- `network` - Network connectivity and configuration rules
- `linux` - OS-level checks (kernel, packages, services)
- `storage` - Storage and filesystem validation

### 3. **Runner** (Top Level)
The main orchestrator that:
- Auto-discovers all domain classes in the `domains` package
- Executes rules in parallel across multiple nodes
- Aggregates results and generates JSON output
- Manages `oc debug` connections and cleanup

**Location:** `src/in_cluster_checks/runner.py`

### Execution Flow

```
Runner (discovers domains)
  └─> Domain 1 (e.g., HWValidationDomain)
       ├─> Rule 1 (e.g., CheckDiskUsage)
       ├─> Rule 2 (e.g., CheckCPUInfo)
       └─> Rule 3 (e.g., CheckMemory)
  └─> Domain 2 (e.g., NetworkValidationDomain)
       ├─> Rule 1 (e.g., CheckNetworkConnectivity)
       └─> Rule 2 (e.g., CheckDNSResolution)
```

When adding new functionality:
- **Adding a check** → Create a new Rule in an existing domain
- **Adding a new category** → Create a new Domain with its rules
- **No registration needed** → The Runner auto-discovers everything

## Adding New Rules

To add a new validation rule follow the following guidelines:

### 1. Create the Rule Class

Create a new rule in the appropriate domain directory (e.g., `src/in_cluster_checks/rules/hw/`):

```python
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives, Status


class YourNewRule(Rule):
    """Brief description of what this rule validates."""

    # Define which nodes this rule applies to
    objective_hosts = [Objectives.ALL_NODES]  # or MASTERS, WORKERS, etc.

    def set_document(self):
        """Set rule metadata."""
        self.unique_name = "your_new_rule"  # Must be unique without spaces in small letters!
        self.title = "Human-readable rule title"

    def run_rule(self):
        """Execute the validation logic."""
        # Run command on the node
        return_code, stdout, stderr = self.run_cmd("your-command")

        # Parse output and determine pass/fail
        if return_code == 0:
            return RuleResult.passed("Validation passed")
        else:
            return RuleResult.failed(f"Validation failed: {stderr}")
```

### 2. Add Rule to Domain

Add your rule to the appropriate domain in `src/in_cluster_checks/domains/`:

```python
from in_cluster_checks.rules.hw.your_file import YourNewRule

class HWValidationDomain(RuleDomain):
    def get_rule_classes(self) -> List[type]:
        return [
            # ... existing rules ...
            YourNewRule,  # Add your rule class here
        ]
```

### 3. Write Tests

Create related tests in `tests/rules/`:

```python
def test_your_new_rule():
    """Test your new rule."""
    rule = YourNewRule()
    # Test with mock data
    # Assert expected behavior
```

### 4. Run Tests

```bash
pytest tests/rules/hw/test_your_new_rule.py -v
```

## Adding New Domains

To add a new domain:

### 1. Create Domain Class

Create a new file in `src/in_cluster_checks/domains/`:

```python
from typing import List
from in_cluster_checks.core.domain import RuleDomain


class YourNewDomain(RuleDomain):
    """Description of this validation domain."""

    def domain_name(self) -> str:
        """Return unique domain name."""
        return "your_domain"

    def get_rule_classes(self) -> List[type]:
        """Return list of rule classes in this domain."""
        return [
            # List your domain's rules here
        ]
```

### 2. Create Rule Directory

Create directory structure:
```
src/in_cluster_checks/rules/your_domain/
├── __init__.py
└── your_validations.py
```

### 3. The Runner Will Auto-Discover It

The `InClusterCheckRunner` automatically discovers all domains in the `domains` package - no manual registration needed!

## Testing Your Changes

### Manual Testing
<!-- is there an option for the developer to edit code on IDE and copy to the env' or we expect them to develop using 'vi' on the env' itself? -->
Test your changes manually using the CLI or programmatically:

```bash
# Using CLI with debug mode to test a specific rule
in-cluster-checks --debug-rule your_rule_name

# Or test programmatically
python -c "
from in_cluster_checks.runner import InClusterCheckRunner
from pathlib import Path

runner = InClusterCheckRunner(
    debug_rule_flag=True,
    debug_rule_name='your_rule_name',
)
runner.run(output_path=Path('./test-results.json'))
"
```

**Debug Mode Features:**
- Only runs the specified rule
- Shows detailed command execution output
- Disables secret filtering for easier debugging <!-- we should explain how to do it -->
- Disables JSON output (shows results in console)

### Automated Testing

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/rules/hw/test_hw_validations.py -v
```

### Run with Coverage
<!-- what does it mean? -->
```bash
pytest --cov=src/in_cluster_checks --cov-report=term-missing
```

### Coverage Requirements

- Minimum coverage: **80%**
- All new code should have tests
- Pre-commit hooks enforce coverage requirements

## Code Style

### Tools

We use the following tools (enforced by pre-commit):

- **black**: Code formatting (line length: 120)
- **flake8**: Linting
- **isort**: Import sorting
- **Custom linter**: No imports inside functions

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
pre-commit run --all-files
```

### Python Style Guidelines

- **Line length**: 120 characters
- **Import order**: stdlib, third-party, local (managed by isort)
  - Group imports with blank lines between categories
  - **ALWAYS place all imports at the top of the file** - never add imports inside functions
- **Docstrings**: Use Google-style docstrings
- **Type hints**: Use type hints where appropriate (Python 3.12+)
- **Naming**:
  - Classes: `PascalCase`
  - Functions/methods: `snake_case`
  - Constants: `UPPER_CASE`
  - Private: prefix with `_`
- **Function return values**: When unpacking function returns, accept exactly the values the function returns
  - Match the number of return values when unpacking tuples
  - Don't use `_` to ignore values unless you genuinely don't need them
  - Example:
    ```python
    # Good - unpacks all three values that run_cmd() returns
    return_code, stdout, stderr = self.run_cmd("df -h")

    # Bad - ignoring stderr when the function returns it
    return_code, stdout, _ = self.run_cmd("df -h")  # Only if stderr is truly unused
    ```

### Code Quality Guidelines

#### Comments

**Only add comments when the code is hard to understand without them.**

- Don't add comments that restate what the code does
- Don't add comments for self-explanatory code or obvious operations
- Only add comments to explain complex algorithms, non-obvious workarounds, or important design decisions

**Examples of unnecessary comments (avoid these):**
```python
self._lock = threading.Lock()  # Prevent parallel execution (obvious from code)
with self._lock:  # Use lock (obvious from context)
self.node_name = node_name  # Set node name (restates what code does)
```

#### Conditional Checks

**Avoid redundant None checks when checking truthiness.**

```python
# Good - concise and Pythonic
if not results:
    return []

# Bad - redundant check
if results is None or not results:
    return []
```

In Python, `not variable` evaluates to `True` for `None`, empty lists `[]`, empty strings `""`, empty dicts `{}`, `0`, and `False`.

#### DRY Principle

**NEVER duplicate logic across multiple files or functions.** Follow the DRY (Don't Repeat Yourself) principle.

When you find similar code in multiple places:
1. Identify the common logic
2. Extract it to a single location (utility function, base class method, etc.)
3. Have all callers use the shared implementation

**Benefits:**
- Changes only need to be made in one place
- Consistent behavior across all code paths
- Easier to test and maintain
- Better separation of concerns
<!-- I don't think it's a good example... -->
### Example

```python
from typing import List

from in_cluster_checks.core.rule import Rule


class MyNewRule(Rule):
    """
    Brief one-line description.

    Longer description if needed. Explain what this rule validates
    and why it's important.

    Returns:
        RuleResult: Validation result with pass/fail status
    """

    objective_hosts = [Rule.Objectives.ALL_NODES]

    def set_document(self):
        """Set rule metadata."""
        self.unique_name = "my_new_rule"
        self.title = "My New Validation Rule"

    def run_rule(self):
        """Execute validation logic."""
        return_code, stdout, stderr = self.run_cmd("echo 'test'")
        return Rule.RuleResult.passed("Validation passed")
```

## Submitting Code Changes

### 1. Update Your Branch

```bash
git fetch upstream
git rebase upstream/main
```

### 2. Push to Your Fork

```bash
git push origin YOUR-FEATURE-NAME
```

### 3. Create Pull Request

1. Go to the [repository on GitHub](https://github.com/sprizend-rh/in-cluster-checks)
2. Click "New Pull Request"
3. Select your fork and branch
4. Fill out the PR template:
   - **Title**: Brief description of changes
   - **Description**: Detailed explanation of what and why
   - **Tests**: How you tested the changes
   - **Related Issues**: Link any related issues

### 4. PR Review Process

- **Automated checks**: CI will run tests and linting
- **Code review**: Maintainers will review your code
- **Feedback**: Address any requested changes
- **Merge**: Once approved, maintainers will merge your PR

### PR Checklist

Before submitting, ensure:

- [ ] Code follows style guidelines (black, flake8, isort pass)
- [ ] All tests pass (`pytest`)
- [ ] Coverage is >= 80%
- [ ] New code has tests
- [ ] Documentation is updated (if needed)
- [ ] Commit messages are clear and descriptive
- [ ] No secrets or sensitive data in code/tests

## Questions?

- **Issues**: Open an issue on GitHub for bugs or feature requests <!-- I should we explain how to do it? -->
- **Discussions**: Use GitHub Discussions for questions
- **Email**: Contact maintainers for private concerns

## License

By contributing, you agree that your contributions will be licensed under the GPL-3.0-or-later license.

Thank you for contributing! 🎉
