---
paths:
  - "src/in_cluster_checks/**/*.py"
  - "tests/**/*.py"
---

# In-Cluster Check Framework

## Architecture

The in-cluster check framework runs direct rule checks on live clusters using `oc debug` for node access.

**Components:**
- `src/in_cluster_checks/core/`: Base classes — Rule, RuleDomain, Operator, executors
- `src/in_cluster_checks/rules/`: Rule implementations by domain (hw, network, linux, storage)
- `src/in_cluster_checks/domains/`: Domain orchestrators that group related rules
- `src/in_cluster_checks/runner.py`: Main runner that discovers domains, builds executors, and coordinates execution
- Uses `oc debug` to run commands directly on cluster nodes

## Execution Flow

1. **Node Discovery**: `NodeExecutorFactory` discovers cluster nodes via `oc get nodes`
2. **Executor Creation**: Creates `NodeExecutor` instances for each node using `oc debug`
3. **Domain Discovery**: `InClusterCheckRunner.discover_domains()` auto-discovers all `RuleDomain` subclasses
4. **Domain Execution**: Each `RuleDomain` runs its rules via `ParallelRunner`
5. **Result Aggregation**: `StructedPrinter` collects results and generates JSON output
6. **Cleanup**: Disconnect from all nodes

## Rule Types

- `Rule` (`core/rule.py`): Standard rule — runs on specific nodes, returns `RuleResult`
- `OrchestratorRule` (`core/rule.py`): Coordinates data collection across ALL nodes, uses `DataCollector`
- `DataCollector` (`core/operations.py`): Collects data from nodes without validation (used by `OrchestratorRule`)
- `HwFwRule` / `HwFwDataCollector` (`rules/hw_fw_details/hw_fw_base.py`): Specialized for hardware/firmware comparison

## Status Model

All rules use the `Status` enum (`utils/enums.py`):
- `Status.PASSED` ("pass"): Rule passed
- `Status.FAILED` ("fail"): Rule failed (critical)
- `Status.WARNING` ("warning"): Non-critical issue
- `Status.INFO` ("info"): Informational only
- `Status.SKIP` ("skip"): Skipped due to exception
- `Status.NOT_APPLICABLE` ("na"): Prerequisite not met

## Key Base Classes

- `RuleDomain` (`core/domain.py`): Groups related rules, runs them via `ParallelRunner`
- `FlowsOperator` (`core/operations.py`): Base with command execution methods (`run_cmd`, `get_output_from_run_cmd`)
- `DataCollector` (`core/operations.py`): Base class for data collection
- `NodeExecutor` (`core/executor.py`): Runs commands on nodes via `oc debug`
- `NodeExecutorFactory` (`core/executor_factory.py`): Node discovery and executor creation
- `StructedPrinter` (`core/printer.py`): Result collection, formatting, and JSON output

## Development Guidelines

**Exception handling:**
- Prefer raising `UnExpectedSystemOutput` (`core/exceptions.py`) when a command produces unexpected output or fails. The framework catches it and converts the result to SKIP status with full details in the JSON output.

**Prerequisites:**
- Always implement `is_prerequisite_fulfilled()` when the rule depends on a specific package, binary, or system condition being present. Return `PrerequisiteResult.not_met("reason")` if the dependency is missing — the framework will mark the result as NOT_APPLICABLE.

**Logging:**
- NEVER use `self.logger` in rules. Return error messages via `RuleResult.failed()` or `RuleResult.warning()` instead. The framework handles logging automatically.

## Existing Domains

- **HwDomain** (`domains/hw_domain.py`): Hardware checks (disk, memory, CPU)
- **NetworkDomain** (`domains/network_domain.py`): Network checks (OVS, DNS, bonding)
- **LinuxDomain** (`domains/linux_domain.py`): Linux system checks (systemd, SELinux, clock)
- **StorageDomain** (`domains/storage_domain.py`): Storage validation
- **HwFwDetailsDomain** (`domains/hw_fw_details_domain.py`): Hardware/firmware information collection
