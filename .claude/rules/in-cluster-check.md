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

**Light-Run Mode:**
- **Use `include_in_light_run`** to mark resource-intensive rules that should be excluded from quick health checks
- Set `include_in_light_run = False` on rules that perform resource-intensive operations (e.g., hardware/firmware inventory collection)
- Default is `True` (included in light runs) — only set to `False` for truly resource-intensive rules
- When `--light-run` CLI flag is used, rules with `include_in_light_run = False` are automatically excluded
- Example:
  ```python
  class HardwareDetailsRule(OrchestratorRule):
      objective_hosts = [Objectives.ORCHESTRATOR]
      unique_name = "hardware_details"
      include_in_light_run = False  # Exclude from --light-run
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

**Detailed Confluence Documentation Guidelines:**

When creating documentation, follow these detailed steps:

**Step 1: Understand the Rule**

Read the rule's source code to understand:
- What it checks (class docstring)
- When it fails (run_rule logic)
- Prerequisites (is_prerequisite_fulfilled)
- KB article reference (look for `Reference:` line in docstring)

Example location: `src/in_cluster_checks/rules/network/ovs_validations.py`

**Step 2: Create Confluence Page**

**Naming convention:** `<Domain>-<Rule-Name>`
- Examples: `Network-OVS-Physical-Port-Health-Check`, `Storage-Disk-Space-Check`

**Template sections (in order):**
1. **Description** - What the rule checks and when it fails (1-3 sentences)
2. **Prerequisites** - Requirements and dependencies
3. **Impact** - Consequences of failure
4. **Root Cause** - Common failure scenarios (2-5 bullet points)
5. **Diagnostics** - Commands to verify what the rule checks
6. **Solution** - Remediation procedures with verification steps
7. **Resources** - Links to documentation and KB articles

**Step 3: Write Description Section**

**Format:**
```markdown
## Description

[1-3 concise sentences explaining what the rule checks and when it fails]
```

**Critical rules:**
- ✅ Start immediately with what the rule checks
- ✅ State when it fails
- ❌ NO metadata fields (Rule Name, Rule Type, Objective Hosts, RCA Reference)
- ❌ NO "Purpose:" header

**Example:**
```markdown
## Description

This rule checks if OVS physical ports attached to the external bridge are properly configured. It verifies that physical ports exist, are UP, and have no IP address assigned.

The rule fails if any physical port is DOWN or has an IPv4 address.
```

**Step 4: Write Prerequisites Section**

**Format:**
```markdown
## Prerequisites

- Network type: OVN-Kubernetes
- Required packages: <list>
- Commands: `command1`, `command2`
```

Or if only basic commands are needed:
```markdown
## Prerequisites

- Commands: `df`, `crictl`
```

**Rules:**
- List all requirements and conditions for rule to run
- Include when rule returns NOT_APPLICABLE (e.g., "OVN-Kubernetes networking required")
- Be specific and complete - readers should know exactly what's needed
- ❌ DO NOT include generic "OpenShift cluster" or "oc debug" - these are implicit for all rules
- Only list specific requirements beyond the basic OpenShift environment

**Step 5: Write Impact, Root Cause, Diagnostics**

**Impact - Lead with most critical consequence:**
```markdown
## Impact

Brief description of what happens when rule fails:

- **Primary impact** - Most critical consequence
- **Secondary impacts** - Other consequences
```

**Root Cause - SHORT bullet points ONLY:**
```markdown
## Root Cause

Common scenarios causing <issue>:

- **Root cause name** - Brief one-line description
- **Root cause name** - Brief one-line description
```

**Rules:**
- ❌ NO sub-bullets, NO examples, NO case numbers
- ✅ One line per cause, 2-5 causes maximum

**Diagnostics - Commands that verify what rule checks:**
```markdown
## Diagnostics

Brief intro:

\`\`\`bash
# Command 1
command1

# Command 2 (replace <placeholder> with your value, e.g., bond0)
command2 <placeholder>
\`\`\`

Expected result.
```

**Rules:**
- ✅ Only commands that verify what the rule checks
- ✅ Use placeholders: `<bridge-name>`, `<interface-name>`, `<device-name>`, etc.
- ✅ Add inline comments explaining what to substitute
- ❌ NO troubleshooting commands (journalctl, systemctl status, oc logs)
- ❌ NO step-by-step procedures

**Step 6: Write Solution Section**

Solutions must be written manually based on rule failure scenarios.

**Format - Use numbered steps or command blocks with descriptions:**
```markdown
## Solution

Brief context or command block with description:

\`\`\`bash
# Commands with placeholders and comments
oc create secret tls <secret-name> -n <namespace> \
  --cert=new-tls.crt --key=new-tls.key \
  --dry-run=client -o yaml | oc apply -f -
\`\`\`

Or use numbered steps for multi-step procedures:

1. Verify operator health

   Ensure operator is running correctly:

   \`\`\`bash
   oc get clusteroperator <operator-name>
   oc get pods -n <namespace>
   \`\`\`

2. Check for known issues

   \`\`\`bash
   oc get events -n <namespace> --sort-by='.lastTimestamp'
   \`\`\`
```

**Rules:**
- ✅ Use numbered steps (1., 2., 3.) for multi-step procedures
- ✅ Use command blocks with brief descriptions for simple fixes
- ✅ Integrate warnings inline: `WARNING: This requires maintenance window`
- ✅ Include verification commands at end when needed
- ❌ Don't use "### Solution N:" headers
- ❌ Don't label solutions as "Recommended" or "Alternative"

**Placeholder rules:**
- ✅ Always use placeholders: `<secret-name>`, `<namespace>`, `<pod-name>`, etc.
- ✅ Add inline comments: `# Replace <placeholder> with your value`
- ❌ Never hardcode environment-specific values

**Common placeholders:**
- Network: `<interface-name>`, `<vlan-interface>`, `<bridge-name>`, `<ip-address>`
- Kubernetes: `<node-name>`, `<namespace>`, `<pod-name>`, `<deployment-name>`, `<secret-name>`
- Storage: `<device-name>`, `<mount-point>`, `<filesystem-type>`
- Hardware: `<cpu-number>`, `<temperature>`, `<threshold>`

**Step 7: Write Resources Section**

**Format:**
```markdown
## Resources

- [Brief description](URL)
- [Brief description](URL)
```

**Critical rules:**
- ✅ **ALWAYS check source code** for `Reference:` line before adding KB article
- ✅ Use markdown link format ONLY: `[Description](URL)`
- ✅ Verify KB article number matches source code exactly
- ❌ NO KB articles if not referenced in source code
- ❌ NO verbose format: `**Label:** URL - description`
- ❌ NO code/test paths or support case links

**What to include:**
- Red Hat KB articles (only if in source code `Reference:` line)
- OpenShift documentation
- External docs (OVS, OVN, NetworkManager, nmstate)
- RFCs (if relevant)

**Example:**
```markdown
## Resources

- [Red Hat KB Article 6250271 - DNS configuration via MachineConfig](https://access.redhat.com/solutions/6250271)
- [OpenShift - OVN-Kubernetes network provider](https://docs.openshift.com/...)
- [nmstate - NodeNetworkConfigurationPolicy](https://nmstate.io/)
```

## Existing Domains

- **HWValidationDomain** (`domains/hw_domain.py`): Hardware checks (disk usage, CPU, memory, temperature)
- **NetworkValidationDomain** (`domains/network_domain.py`): Network connectivity and configuration (OVN-K8s, OVS, Whereabouts)
- **LinuxValidationDomain** (`domains/linux_domain.py`): OS-level checks (kernel, packages, services)
- **StorageValidationDomain** (`domains/storage_domain.py`): Storage and filesystem checks
- **K8sValidationDomain** (`domains/k8s_domain.py`): Kubernetes-specific checks
- **EtcdValidationDomain** (`domains/etcd_domain.py`): etcd cluster health checks
- **SecurityValidationDomain** (`domains/security_domain.py`): Security-related checks (certificate expiry)
- **HwFwDetailsDomain** (`domains/hw_fw_details_domain.py`): Hardware and firmware inventory collection
