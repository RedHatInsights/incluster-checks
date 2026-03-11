# Testing

## Test Framework Setup

**IMPORTANT**: Always source the virtual environment before running tests:
```bash
source .venv/bin/activate
pytest
```

## Testing Methods
- **Pre-commit Checks**: Run `pre-commit run --all-files` to validate code quality, formatting, and tests
- **Unit Tests**: Run `pytest` (requires venv activation)
- **Coverage Check**: `pytest --cov=src/in_cluster_checks --cov-report=term-missing` - measures which lines of code are executed during tests, shows missing coverage

## Test Commands

**Run all tests:**
```bash
source .venv/bin/activate
pytest
```

**Run with coverage:**
```bash
pytest --cov=src/in_cluster_checks --cov-report=term-missing
```

**Run specific test file:**
```bash
pytest tests/rules/hw/test_hw_validations.py -v
```

**Run specific test class:**
```bash
pytest tests/rules/hw/test_hw_validations.py::TestCheckDiskUsage -v
```

**Run pre-commit checks (includes tests):**
```bash
pre-commit run --all-files
```

## Manual Testing

Test specific rules using the CLI:

```bash
# Test a specific rule in debug mode (disables secret filtering)
in-cluster-checks --debug-rule your_rule_name

# Run all checks with debug logging
in-cluster-checks --log-level DEBUG --output ./test-results.json
```

## Test Structure

Tests are organized by component:
- `tests/core/`: Core framework tests
- `tests/domains/`: Domain orchestrator tests
- `tests/rules/`: Individual rule tests
- `tests/pytest_tools/`: Test utilities and base classes

## Writing Rule Tests

Use the `RuleTestBase` framework for consistent rule testing:

```python
import pytest

from in_cluster_checks.rules.hw.hw_validations import CheckDiskUsage
from tests.pytest_tools.test_operator_base import CmdOutput
from tests.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class TestCheckDiskUsage(RuleTestBase):
    """Test CheckDiskUsage rule."""

    tested_type = CheckDiskUsage

    df_output_ok = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda1      ext4       50G   30G   18G  63% /
/dev/sdb1      xfs       100G   50G   46G  53% /data
"""

    df_output_error = """Filesystem     Type      Size  Used Avail Use% Mounted on
/dev/sda1      ext4       50G   47G    1G  98% /
"""

    df_cmd = "df -hT -x tmpfs -x devtmpfs -x overlay -x composefs -x efivarfs -x squashfs -x iso9660"

    scenario_passed = [
        RuleScenarioParams(
            "disk usage below warning threshold",
            {df_cmd: CmdOutput(df_output_ok)},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "disk usage above error threshold (>90%)",
            {df_cmd: CmdOutput(df_output_error)},
            failed_msg="Disk usage critical:\n/dev/sda1 (mounted on: /) usage is 98% (threshold: 90%)",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
```

### CmdOutput usage
```python
CmdOutput("stdout text")                          # Success (rc=0)
CmdOutput("stdout text", return_code=1)            # Failed command
CmdOutput("stdout text", return_code=0, err="")    # Full form
```
