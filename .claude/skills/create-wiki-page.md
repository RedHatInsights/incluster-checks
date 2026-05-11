Create a wiki page for an in-cluster-checks validation rule.

$ARGUMENTS

Follow the 7-section wiki template and project documentation standards.

---

## Step 1: Understand the Rule

Read the rule's source code to understand:
- What it checks (class docstring)
- When it fails (run_rule logic)
- Prerequisites (is_prerequisite_fulfilled)
- KB article reference (look for `Reference:` line in docstring)

Example location: `src/in_cluster_checks/rules/network/ovs_validations.py`

## Step 2: Create Wiki Page

**Naming convention:** `<Domain>-<Rule-Name>.md`
- Examples: `Network-OVS-Physical-Port-Health-Check.md`, `Storage-Disk-Space-Check.md`

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

- OpenShift cluster with <network type>
- Required packages: <list>
- Commands: `command1`, `command2`
```

**Rules:**
- List all requirements and conditions for rule to run
- Include when rule returns NOT_APPLICABLE (e.g., "OVN-Kubernetes networking required")
- Be specific and complete - readers should know exactly what's needed

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

## Checklist

- [ ] All 7 sections present (Description, Prerequisites, Impact, Root Cause, Diagnostics, Solution, Resources)
- [ ] Description is concise (1-3 sentences, no metadata fields)
- [ ] Root Cause is SHORT (2-5 causes, brief bullets only)
- [ ] Diagnostics is CONCISE (command block + expected result, no troubleshooting)
- [ ] All commands use placeholders (e.g., `<interface-name>`, not `bond0`)
- [ ] Placeholders have inline comments with examples
- [ ] Resources KB article verified against source code Reference: line
- [ ] Resources use markdown link format `[Description](URL)`
- [ ] Solutions use numbered steps or command blocks with descriptions
- [ ] Verification commands included where needed
- [ ] Critical warnings included (e.g., MachineConfig + nmcli for OVS VLANs)
