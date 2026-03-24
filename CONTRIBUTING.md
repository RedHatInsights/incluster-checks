# Contributing to In-Cluster Checks

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Table of Contents

- [About In-Cluster Checks](#about-in-cluster-checks)
- [Understanding the Framework](#understanding-the-rules-hierarchy)
- [Development Setup](#development-setup)
- [Making Code Changes](#making-code-changes)
- [Adding New Rules](#adding-new-rules)
- [Adding New Domains](#adding-new-domains)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting Code Changes](#submitting-code-changes)
- [Questions](#questions)


## About In-Cluster Checks

In-Cluster Checks is a generic framework for running health validation rules **directly on OpenShift cluster nodes in real-time** using `oc debug`.

**What makes it special:**

This approach offers:


- **Direct node access** - Commands run on actual nodes, not from external collectors
- **On-the-fly execution** - No pre-collected data needed; validations happen when you run them
- **Real-time diagnostics** - Immediate feedback on node health and configuration
- **Relevant rule execution** - Only relevant rules run based on prerequisite checks
- **Fast execution** - Parallel rule execution across multiple nodes
- **Easy debugging** - Full visibility into commands executed for each rule

The framework has been extracted from **Pendrive** project as open-source to benefit the broader OpenShift community, providing a generic infrastructure for anyone to build custom health check rules.

### ⚠️ Important Safety Disclaimer

**Because In-Cluster Checks runs commands directly on cluster nodes, you must carefully review your code before submitting:**

- **Use read-only commands only** - Rules should observe and report, never modify cluster state
- **No destructive operations** - Do not use commands that modify, delete, or change any data on the cluster
- **Review every command** - Before pushing your code, verify that all commands are safe and non-destructive
- **Test in non-production first** - Always test new rules in development/test environments

Your responsibility as a contributor is to ensure that the commands in your rules cannot cause harm to the cluster, even if executed repeatedly or in parallel.


## Understanding the Rules Hierarchy

The in-cluster-checks framework is organized into a three-level hierarchy:

### 1. **Rules** (Bottom Level)
Individual rules that run on cluster nodes. Each rule:
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
- `hw` - Hardware checks (disk usage, CPU, memory, temperature)
- `network` - Network connectivity and configuration (OVN-K8s, OVS, Whereabouts)
- `linux` - OS-level checks (kernel, packages, services)
- `storage` - Storage and filesystem checks
- `k8s` - Kubernetes-specific checks
- `etcd` - etcd cluster health checks
- `security` - Security-related checks (certificate expiry)
- `hw_fw_details` - Hardware and firmware inventory collection

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
- **Adding a rule** → Create a new Rule in an existing domain
- **Adding a new domain** → Create a new Domain with its rules, only if it's not covered yet


## Adding New Rules

To add a new rule, follow these guidelines:

### 1. Create the Rule Class

Create a new rule in the appropriate domain directory (e.g., `src/in_cluster_checks/rules/hw/hw_validations.py`):

```python
from in_cluster_checks.core.rule import Rule
from in_cluster_checks.core.rule_result import RuleResult
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.utils.safe_cmd_string import SafeCmdString

class YourNewRule(Rule):
    """Rule description - what this rule verifies."""

    # Define which nodes this rule applies to
    objective_hosts = [Objectives.ALL_NODES]  # or MASTERS, WORKERS, etc.
    unique_name = "your_new_rule"  # Must be unique, lowercase with underscores
    title = "Human-readable rule title"
    links = [
        "https://link-to-documentation-or-kb-article",
    ]

    def run_rule(self):
        """Execute the rule logic."""
        # Use SafeCmdString for all commands (see Command Security section below)
        cmd = SafeCmdString("cat {file}").format(file="/etc/hostname")
        return_code, stdout, stderr = self.run_cmd(cmd)

        # Parse output and determine pass/fail
        if return_code == 0:
            return RuleResult.passed("Rule passed")
        else:
            return RuleResult.failed(f"Rule failed: {stderr}")
```

**Command Security - SafeCmdString:**

**REQUIRED** for all `run_cmd()`, `get_output_from_run_cmd()`, and `run_rsh_cmd()` to prevent command injection.

**Why is SafeCmdString critical?**

SafeCmdString provides multi-layer protection against shell injection attacks. Without it, user-controlled values or dynamic data could be interpreted as shell commands, potentially allowing execution of arbitrary commands on cluster nodes. SafeCmdString validates all variables inserted into commands, ensuring they match safe patterns (paths, identifiers, etc.) and cannot contain shell metacharacters or command separators. This is essential because In-Cluster Checks runs commands directly on production cluster nodes.

**Examples:**
```python
# Static command
self.run_cmd(SafeCmdString("systemctl status"))

# Named placeholder
cmd = SafeCmdString("cat {file}").format(file="/etc/hostname")
self.run_cmd(cmd)

# Positional placeholder
cmd = SafeCmdString("cat {}").format("/etc/hostname")
self.run_cmd(cmd)

# Concatenation with + operator
self.run_cmd(SafeCmdString("cat /etc/hostname") + SafeCmdString("| grep localhost"))

# SafeCmdString as variable (bypasses validation - already safe)
cmd1 = SafeCmdString("etcdctl version")
cmd2 = SafeCmdString("Running: {cmd}").format(cmd=cmd1)
self.run_rsh_cmd(namespace, pod, cmd2)
```

**Allowed patterns in format() variables:**
- Absolute paths: `/var/log/messages`, `/etc/file.conf` (one dot max for extension)
- Generic identifiers: `[a-zA-Z0-9 ]+` (letters, digits, spaces only - no leading dashes)
- Etcd URLs: `https://etcd-N.etcd.openshift-etcd.svc:2379/path`
- PCI addresses: `01:00.0`, `0000:01:00.0`

**Pre-commit linter enforces:**
- Template must be string literal (not variable/f-string/expression)
- One SafeCmdString per line (except `SafeCmdString() + SafeCmdString()` is allowed)

**Pre-commit Blocked patterns:**
```python
check_cmd = "systemctl status"
SafeCmdString(check_cmd)         # Variable - BLOCKED

SafeCmdString(f"cat {file}")     # f-string - BLOCKED

SafeCmdString("cat " + file)     # Expression - BLOCKED
```

**Pre-commit failure example:**
```python
check_cmd = "systemctl status"
cmd = SafeCmdString(check_cmd)
return_code, out, err = self.run_cmd(cmd)
```

Output:
```
Check SafeCmdString usage................................................Failed
- hook id: safe-cmd-string-check
- exit code: 1

Found unsafe SafeCmdString usage:

  src/in_cluster_checks/rules/<domain>/<file>.py:53: SafeCmdString() only accepts literal strings, not variables ('check_cmd'). Use SafeCmdString('template {var}').format(var=...) instead.

Use SafeCmdString('template {var}').format(var=...) for safe command formatting.
This validates variables to prevent shell injection.
```

**Best Practices:**
- Use descriptive `unique_name` values (e.g., `is_disk_space_sufficient`, `is_network_reachable`)
- Include helpful error messages in failed results
- Use `RuleResult.warning()` for non-critical issues
- Parse command output carefully and handle edge cases

**Command Execution Best Practices:**
- **Run simple commands** - Execute basic commands and parse the output in Python
- **Parse in Python, not in shell** - Use Python's string methods, regex, and parsing libraries instead of chaining multiple shell commands
- **Avoid command chaining** - Don't use multiple pipes (`|`) with `grep`, `awk`, `sed`, etc.
- **Single grep is acceptable** - Using one `grep` to filter relevant lines is fine (e.g., `cat /proc/meminfo | grep MemTotal`)
- **Never use `awk`** - Parse text in Python instead of using `awk` in commands


### 2. Add Rule to Domain

Add your rule to the appropriate domain in `src/in_cluster_checks/domains/`:

```python
from in_cluster_checks.rules.hw.hw_validations import YourNewRule

class HWValidationDomain(RuleDomain):
    def get_rule_classes(self) -> List[type]:
        return [
            # ... existing rules ...
            YourNewRule,  # Add your rule class here
        ]
```

### 3. Write Tests

Create tests in the appropriate test file (e.g., `tests/rules/hw/test_hw_validations.py`):

```python
import pytest

from in_cluster_checks.rules.hw.hw_validations import YourNewRule
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import RuleTestBase, RuleScenarioParams


class TestYourNewRule(RuleTestBase):
    """Test YourNewRule."""

    tested_type = YourNewRule

    scenario_passed = [
        RuleScenarioParams(
            "rule passes when condition is met",
            {"your-command": CmdOutput("expected output")},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "rule fails when condition is not met",
            {"your-command": CmdOutput("error output", return_code=1)},
            failed_msg="Rule failed: error output",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
```

### 4. Run Tests

```bash
# Activate virtual environment first
source .venv/bin/activate

# Run specific test
pytest tests/rules/hw/test_hw_validations.py::TestYourNewRule -v

# Run all tests
pytest

# Run with coverage
pytest --cov=src/in_cluster_checks --cov-report=term-missing
```

## Adding New Domains

To add a new domain (only if the functionality doesn't fit existing domains):

### 1. Create Domain Class

Create a new file in `src/in_cluster_checks/domains/` (e.g., `your_domain.py`):

```python
from typing import List

from in_cluster_checks.core.domain import RuleDomain
from in_cluster_checks.rules.your_domain.your_rules import YourRule1, YourRule2


class YourDomain(RuleDomain):
    """Description of this rule domain."""

    def domain_name(self) -> str:
        """Return unique domain name."""
        return "your_domain"

    def get_rule_classes(self) -> List[type]:
        """Return list of rule classes in this domain."""
        return [
            YourRule1,
            YourRule2,
        ]
```

### 2. Create Rule Directory

Create directory structure for your rules:
```
src/in_cluster_checks/rules/your_domain/
├── __init__.py
└── your_rules.py
```

### 3. Create Tests

Create test directory:
```
tests/domains/test_your_domain.py
tests/rules/your_domain/
├── __init__.py
└── test_your_rules.py
```

### 4. Auto-Discovery

The `InClusterCheckRunner` automatically discovers all domains in the `domains` package - no manual registration needed!

## Code Style

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
- **Function return values**: When unpacking function returns, accept exactly the values the function returns.

### Code Quality Guidelines

#### Comments

**Only add comments when the code is hard to understand without them.**

- Don't add comments that restate what the code does
- Don't add comments for self-explanatory code or obvious operations
- Only add comments to explain complex algorithms, non-obvious workarounds, or important design decisions


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

## Testing

### Running Tests

Always activate the virtual environment before running tests:

```bash
source .venv/bin/activate
```

### Test Commands

**Run specific test file:**
```bash
pytest tests/rules/hw/test_hw_validations.py -v
```

**Run specific test class:**
```bash
pytest tests/rules/hw/test_hw_validations.py::TestCheckDiskUsage -v
```

### Manual Testing
Rules that work on one cluster configuration might fail or produce incorrect results on others. Therefore, **test new rules on various environments** to verify your code handles different cluster configurations:

- **Different versions** - Test on multiple versions when possible
- **Different node types** - Test on worker nodes, master nodes, and different infrastructure platforms (bare metal, VMs, cloud providers)
- **Different configurations** - Verify on nodes with varying hardware specs and operating system versions (RHCOS/RHEL)
- **Edge cases** - Test on nodes where certain features may not be available (e.g., cpufreq files missing on VMs)

**Testing commands:**

```bash
# Test a specific rule in debug mode (disables secret filtering)
in-cluster-checks --debug-rule your_rule_name

# Run all checks with debug logging
in-cluster-checks --log-level DEBUG --output ./test-results.json
```

### Writing Tests

See the [Adding New Rules](#adding-new-rules) section for test examples using the `RuleTestBase` framework.

## Development Setup

### Recommended Development Environment

We recommend developing and testing directly on a machine with OpenShift cluster access. You can edit code using an IDE connected to the remote server via SSH (e.g., [VSCode Remote SSH](https://code.visualstudio.com/docs/remote/ssh)) while running tests locally on that environment.

### Prerequisites
- Python >= 3.12
- Access to an OpenShift cluster (for integration testing)
- `oc` CLI tool installed

### Clone the Repository

1. **Set up SSH key with GitHub** (recommended for easier authentication):

   If you don't have an SSH key configured with GitHub, follow these steps:

   a. Generate an SSH key (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   # Press Enter to accept default file location
   # Optionally set a passphrase
   ```

   b. Add the SSH key to your GitHub account:
   ```bash
   # Display your public key
   cat ~/.ssh/id_ed25519.pub
   # Copy the output
   ```

   c. Go to GitHub → Settings → SSH and GPG keys → New SSH key, paste your public key and save

   d. Test your connection:
   ```bash
   ssh -T git@github.com
   # You should see: "Hi USERNAME! You've successfully authenticated..."
   ```

2. **Fork the repository** on GitHub: https://github.com/sprizend-rh/in-cluster-checks

3. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR-USERNAME/in-cluster-checks.git
   cd in-cluster-checks
   ```

4. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/sprizend-rh/in-cluster-checks.git
   ```

### Install Dependencies

1. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install development dependencies**:
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

If all tests pass and pre-commit runs successfully, your development environment is ready!

### Making Code Changes

1. **Create a new branch**:

    Always work on a local branch - Never commit directly to the `main` branch:
   ```bash
   git checkout -b YOUR-FEATURE-NAME
   ```

2. **Make your changes** following the [Code Style](#code-style) guidelines

3. **Test your changes**:

    **Manual testing** - Test specific rules you've added or modified:
    ```bash
    source .venv/bin/activate
    in-cluster-checks --debug-rule your_rule_name
    ```

    **Automated testing** - Run pre-commit checks (includes code style and pytest):
    ```bash
    pre-commit run --all-files
    ```

    See the [Testing](#testing) section for more detailed testing options and commands.

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

### Submitting Code Changes

1. **Update Your Branch**

    Sync with the latest changes from upstream:
    ```bash
    git fetch upstream
    git rebase upstream/main
    ```

2. **Push to Your Fork**

    ```bash
    git push origin YOUR-FEATURE-NAME
    ```

3. **Create Pull Request**

    **Option 1: Using the link from push output**
    1. Click the pull request link displayed after pushing
    2. Fill out the PR template
    3. Click "Create pull request"

    **Option 2: Via GitHub**
    1. Go to the [repository on GitHub](https://github.com/sprizend-rh/in-cluster-checks)
    2. Click "New Pull Request"
    3. Select your fork and branch
    4. Fill out the PR template

    **PR Template Information:**
    - **Title**: Brief description of changes
    - **Description**: Detailed explanation of what and why
    - **Tests**: How you tested the changes
    - **Related Issues**: Link any related issues

4. **PR Review Process**

    - **Automated checks**: CI runs tests and linting automatically
    - **Code review**: Maintainers review your code
    - **Feedback**: Address any requested changes
    - **Merge**: Once approved, maintainers merge your PR

### PR Checklist

Before submitting your PR, ensure:

- [ ] Code follows project style guidelines (`pre-commit run --all-files` passes)
- [ ] All tests pass (`pytest`)
- [ ] Code coverage is maintained or improved
- [ ] New rules have corresponding tests
- [ ] Documentation is updated (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] No secrets or sensitive data in code/tests
- [ ] Manual testing completed (for rules: `in-cluster-checks --debug-rule your_rule_name`)

## Questions?

- **Bug reports or feature requests**: [Open an issue](https://github.com/sprizend-rh/in-cluster-checks/issues/new) on GitHub
- **General questions**: [Open an issue](https://github.com/sprizend-rh/in-cluster-checks/issues/new) with your question
- **Documentation and rule information**: Check the [project wiki](https://github.com/sprizend-rh/in-cluster-checks/wiki) for detailed knowledge sharing about rules
- **Private matters**: Contact maintainers directly via GitHub

## License

By contributing, you agree that your contributions will be licensed under the BSD 3-Clause License.

Thank you for contributing!
