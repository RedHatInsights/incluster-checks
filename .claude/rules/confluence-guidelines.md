# Confluence Documentation Guidelines

This guide provides detailed instructions for creating Confluence documentation pages for in-cluster validation rules.

## Overview

Every new rule MUST have a corresponding documentation page in Confluence hosted at:  
https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418417677/In-Cluster+Checks+Rules

Create the documentation page in Confluence under the appropriate domain (DPF, Hardware, K8s, Linux, Network, Resources, Security).

## Step 1: Understand the Rule

Read the rule's source code to understand:
- What it checks (class docstring)
- When it fails (run_rule logic)
- Prerequisites (is_prerequisite_fulfilled)
- KB article reference (look for `Reference:` line in docstring)

Example location: `src/in_cluster_checks/rules/network/ovs_validations.py`

## Step 2: Create Confluence Page

**Title convention:** Use the rule's `title` field exactly as defined in the class.
- Examples: `Verify infrastructure pods are ready and running`, `TLS certificate expiry`, `Check deployment replicas status`
- The page is placed under the appropriate domain parent page (K8s, Network, Security, etc.), so no domain prefix is needed in the title.

**Domain parent page IDs** (under [In-Cluster Checks Rules](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418417677)):
- DPF: `418450735`
- Hardware: `418418340`
- K8s: `418516155`
- Linux: `418482835`
- Network: `418482854`
- Resources: `418450807`
- Security: `418516403`

**Space ID:** `377096307`

**Create pages using the Confluence MCP tool:**
```python
mcp__plugin_atlassian_atlassian__createConfluencePage(
  cloudId: "redhat.atlassian.net",
  spaceId: "377096307",
  parentId: "<domain-parent-page-id>",
  title: "<rule-title>",
  contentFormat: "html",
  body: "<page-content>"
)
```

**Template sections (in order):**
1. **Description** - What the rule checks and when it fails (1-3 sentences)
2. **Prerequisites** - Requirements and dependencies
3. **Impact** - Consequences of failure
4. **Root Cause** - Common failure scenarios (2-5 bullet points)
5. **Diagnostics** - Commands to verify what the rule checks
6. **Solution** - Remediation procedures with verification steps
7. **Resources** - Links to documentation and KB articles

## Step 3: Write Description Section

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

## Step 4: Write Prerequisites Section

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

## Step 5: Write Impact, Root Cause, Diagnostics

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

## Step 6: Write Solution Section

**CRITICAL SAFETY REQUIREMENTS:**

Solutions must be **safe and verified** with **zero risk** to user environments:

- ✅ **ONLY provide solutions you are absolutely certain are safe**
- ✅ **Include verification steps** before and after any changes
- ✅ **Use dry-run flags** wherever possible (e.g., `--dry-run=client`)
- ✅ **Warn about maintenance windows** for operations requiring downtime
- ❌ **NEVER suggest destructive operations** (node reboots, deletions, force operations) without explicit warnings
- ❌ **NEVER provide solutions you are uncertain about**

**When uncertain about the correct solution:**
- Direct users to contact support teams or consult official documentation
- Provide diagnostic commands to gather information
- Clearly state when expert assistance is recommended

Before finalizing the solution section, verify that all commands are safe and include appropriate warnings for potentially dangerous operations.

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

## Step 7: Write Resources Section

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

## Documentation Page Examples

- [TLS certificate expiry](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418482936)
- [Node certificate expiry](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/418418558)
- [Verify infrastructure pods are ready and running](https://redhat.atlassian.net/wiki/spaces/PDRIVE/pages/435226813)
