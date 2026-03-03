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
- **Coverage Check**: `pytest --cov=src/in_cluster_checks --cov-report=term-missing`

## Testing Workflow

1. **Local unit tests**:
   - Activate venv: `source .venv/bin/activate`
   - Run pre-commit: `pre-commit run --all-files`
   - Run tests: `pytest --cov=src/in_cluster_checks --cov-report=term-missing`

2. **Integration testing** (requires live cluster):
   - Ensure `oc login` to a test cluster
   - Run: `openshift-checks --output ./test-results.json`
   - Verify JSON output format

## Test Structure

Tests are organized by component:
- `tests/unit/core/`: Core framework tests
- `tests/unit/domains/`: Domain orchestrator tests
- `tests/unit/rules/`: Individual rule tests
- `tests/integration/`: End-to-end integration tests (requires cluster access)

## Writing Rule Tests

Use the `RuleTestBase` framework for consistent rule testing:

```python
import pytest

from in_cluster_checks.rules.hw.disk_usage import CheckDiskUsage
from tests.unit.pytest_tools.test_operator_base import CmdOutput
from tests.unit.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class TestCheckDiskUsage(RuleTestBase):
    """Test CheckDiskUsage rule."""

    tested_type = CheckDiskUsage

    good_output = "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       100G   50G   50G  50% /"
    bad_output = "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1       100G   95G    5G  95% /"

    scenario_passed = [
        RuleScenarioParams(
            "disk usage below threshold",
            {"df -h": CmdOutput(good_output)},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "disk usage above threshold",
            {"df -h": CmdOutput(bad_output)},
            failed_msg="Disk usage above 90%",
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
