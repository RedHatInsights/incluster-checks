Create a new in-cluster rule based on the following description:

$ARGUMENTS

Follow the framework guidelines and development rules defined in:
@.claude/rules/in-cluster-check.md

---

## Step 1: Determine the Rule Type

Based on the description, choose ONE type (see "Rule Types" in the linked guidelines above):

- **Rule** — most common, runs on specific nodes
- **OrchestratorRule** — coordinates data collection across ALL nodes, requires a `DataCollector`
- **DataCollector** — collects data from nodes, used BY `OrchestratorRule`

## Step 2: Create the Rule Class

Place the rule in the appropriate file under `src/in_cluster_checks/rules/<domain>/`.
Use an existing domain folder or create a new one with an `__init__.py`.

### Standard Rule Template

```python
from in_cluster_checks.core.rule import Rule, RuleResult, PrerequisiteResult
from in_cluster_checks.utils.enums import Objectives

class MyRuleName(Rule):
    """One-line description of what this rule validates."""

    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "my_rule_name"
    title = "Description shown in reports"

    def is_prerequisite_fulfilled(self):
        """Optional: Check if rule can run on this node."""
        return_code, _, _ = self.run_cmd("which some_tool")
        if return_code != 0:
            return PrerequisiteResult.not_met("some_tool is not available on this system")
        return PrerequisiteResult.met()

    def run_rule(self):
        return_code, out, err = self.run_cmd("some_command")

        if validation_failed:
            return RuleResult.failed("Description of what failed")
        elif has_warnings:
            return RuleResult.warning("Description of warning")
        else:
            return RuleResult.passed()
```

### OrchestratorRule Template (multi-node comparison)

```python
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule, RuleResult
from in_cluster_checks.utils.enums import Objectives

class MyDataCollector(DataCollector):
    """Collect data from each node."""
    objective_hosts = [Objectives.ALL_NODES]
    unique_name = "collect_my_data"
    title = "Collect my data"

    def collect_data(self, **kwargs):
        output = self.get_output_from_run_cmd("some_command")
        return parsed_data

class MyOrchestratorRule(OrchestratorRule):
    """Compare data across all nodes."""
    objective_hosts = [Objectives.ORCHESTRATOR]
    unique_name = "my_orchestrator_rule"
    title = "Compare data across nodes"

    def run_rule(self):
        all_data = self.run_data_collector(MyDataCollector)
        if mismatch_found:
            return RuleResult.failed("Data mismatch across nodes")
        return RuleResult.passed()
```

## Step 3: Register in Domain

Add the new rule class to the appropriate domain in `src/in_cluster_checks/domains/`:

```python
from in_cluster_checks.rules.<domain>.<file> import MyRuleName

class SomeDomain(RuleDomain):
    def get_rule_classes(self) -> List[type]:
        return [
            # ... existing rules ...
            MyRuleName,
        ]
```

If a new domain is needed, create it following `hw_domain.py` as a template.

## Step 4: Write Tests

Create tests in `tests/unit/rules/<domain>/test_<file>.py`:

```python
import pytest

from in_cluster_checks.rules.<domain>.<file> import MyRuleName
from tests.unit.pytest_tools.test_operator_base import CmdOutput
from tests.unit.pytest_tools.test_rule_base import (
    RuleTestBase,
    RuleScenarioParams,
)


class TestMyRuleName(RuleTestBase):
    """Test MyRuleName rule."""

    tested_type = MyRuleName

    good_output = "expected good output here"
    bad_output = "expected bad output here"

    scenario_passed = [
        RuleScenarioParams(
            "description of passing scenario",
            {"exact_command_string": CmdOutput(good_output)},
        ),
    ]

    scenario_failed = [
        RuleScenarioParams(
            "description of failing scenario",
            {"exact_command_string": CmdOutput(bad_output)},
            failed_msg="exact expected failure message",
        ),
    ]

    @pytest.mark.parametrize("scenario_params", scenario_passed)
    def test_scenario_passed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_passed(self, scenario_params, tested_object)

    @pytest.mark.parametrize("scenario_params", scenario_failed)
    def test_scenario_failed(self, scenario_params, tested_object):
        RuleTestBase.test_scenario_failed(self, scenario_params, tested_object)
```

Also update the domain test file to include the new rule in assertions.

### CmdOutput usage
```python
CmdOutput("stdout text")                          # Success (rc=0)
CmdOutput("stdout text", return_code=1)            # Failed command
CmdOutput("stdout text", return_code=0, err="")    # Full form
```

### For OrchestratorRule tests, use data_collector_dict
```python
RuleScenarioParams(
    "scenario name",
    cmd_input_output_dict={},
    data_collector_dict={
        MyDataCollector: {"node1": data1, "node2": data2},
    },
)
```

## Step 5: Run Tests

```bash
source .venv/bin/activate
pytest tests/unit/rules/<domain>/test_<file>.py -v
```

---

## Important Guidelines

**NEVER use `self.logger` in rules** - Return error messages via `RuleResult.failed()` or `RuleResult.warning()` instead. The framework handles logging automatically.

## Checklist

- [ ] Rule class created with `objective_hosts`, `unique_name`, `title`
- [ ] `run_rule()` implemented returning `RuleResult`
- [ ] `is_prerequisite_fulfilled()` added if rule requires specific tools/conditions
- [ ] `UnExpectedSystemOutput` used for command failures
- [ ] NO use of `self.logger` in rule - return error messages via RuleResult
- [ ] Rule registered in the appropriate domain's `get_rule_classes()`
- [ ] Tests written with both `scenario_passed` and `scenario_failed`
- [ ] Domain test updated to include new rule
- [ ] All command strings in tests match EXACTLY what the rule executes
- [ ] Tests pass: `pytest tests/unit/ -v`
- [ ] Imports at top of file, following PEP 8 order
