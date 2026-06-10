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
- Implement `is_prerequisite_fulfilled()` ONLY when checking optional packages, binaries, or system conditions that may not exist. NOT required for core K8s resources (Nodes, Pods, etc). Return `PrerequisiteResult.not_met("reason")` if missing — the framework will mark the result as NOT_APPLICABLE.

**Supported Profiles:**
- **By default, prefer adding `supported_profiles`** to new rules to indicate which deployment profiles they apply to
- Set `supported_profiles` as a class variable with a set of profile names (e.g., `supported_profiles = {"telco-base"}`)
- Only omit `supported_profiles` (leaving default `{"general"}`) for truly generic rules that apply to ANY cluster type
- Rules are automatically filtered based on the active profile — only rules matching the profile hierarchy are executed
- Common profiles: `"general"` (default, all clusters), `"telco-base"` (telco-specific checks)
- Example:
  ```python
  class VerifyNFDOperatorHealth(Rule):
      supported_profiles = {"telco-base"}  # Only runs for telco profiles
      title = "Verify NFD operator health"
      # ...
  ```

**Logging:**
- NEVER use `self.logger` in rules. Return error messages via `RuleResult.failed()` or `RuleResult.warning()` instead. The framework handles logging automatically.

**Documentation:**
- **REQUIRED**: Every new rule MUST have a corresponding documentation page in Confluence
- Rule documentation is hosted at: https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418417677/In-Cluster+Checks+Rules
- When implementing a new rule:
  1. Add the Confluence page link to the rule's `links` field: `links = ["https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/{PAGE_ID}"]`
  2. Create the documentation page in Confluence under the appropriate domain (DPF, Hardware, K8s, Linux, Network, Resources, Security)

**Creating Documentation Page Content:**
- **Workflow**:
  1. Read an existing Confluence page as a template (e.g., [TLS certificate expiry](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482936))
  2. Create the new documentation page in Confluence under the appropriate domain
  3. Add the Confluence page URL to the rule's `links` field

**Documentation Page Structure:**
All documentation pages should follow this standard structure:
  - **Description**: What the rule checks, why it's important, severity level, and failure thresholds
  - **Prerequisites**: Required access, tools, or conditions needed to run the check
  - **Impact**: What happens if the condition fails (specific failure scenarios and consequences)
  - **Root Cause**: Common reasons why this condition occurs
  - **Diagnostics**: Commands and procedures to investigate the issue manually
  - **Solution**: Step-by-step remediation instructions with code examples
  - **Resources**: Links to official documentation, KCS articles, troubleshooting guides

**Documentation Page Examples:**
- See existing templates: [Security - TLS certificate expiry](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482936), [Security - Node certificate expiry](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418558)

## Existing Domains

- **HWValidationDomain** (`domains/hw_domain.py`): Hardware checks (disk usage, CPU, memory, temperature)
- **NetworkValidationDomain** (`domains/network_domain.py`): Network connectivity and configuration (OVN-K8s, OVS, Whereabouts)
- **LinuxValidationDomain** (`domains/linux_domain.py`): OS-level checks (kernel, packages, services)
- **StorageValidationDomain** (`domains/storage_domain.py`): Storage and filesystem checks
- **K8sValidationDomain** (`domains/k8s_domain.py`): Kubernetes-specific checks
- **EtcdValidationDomain** (`domains/etcd_domain.py`): etcd cluster health checks
- **SecurityValidationDomain** (`domains/security_domain.py`): Security-related checks (certificate expiry)
- **HwFwDetailsDomain** (`domains/hw_fw_details_domain.py`): Hardware and firmware inventory collection
