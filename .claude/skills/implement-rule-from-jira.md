Create a new in-cluster validation rule from a Jira ticket.

**Args**: Jira ticket number (e.g., PDRIVE-123)

**Purpose**: This skill helps external contributors implement new validation rules according to project guidelines. It validates the ticket type, scaffolds the rule, creates tests, generates wiki documentation, and handles the complete PR workflow.

# Implement New Rule from Jira Ticket

You are helping an external contributor create a new in-cluster validation rule from a Jira ticket.

## Step 1: Validate Ticket Type

**CRITICAL**: This skill is ONLY for creating new validation rules, not general implementation tasks.

1. **Fetch the Jira ticket**:
   - Use `mcp__plugin_atlassian_atlassian__getJiraIssue` with the ticket number
   - Extract: title, description, issue type, acceptance criteria

2. **Validate issue type**:
   - **REQUIRED**: Issue type MUST be "Story"
   - If the issue type is NOT "Story", **STOP IMMEDIATELY** and inform the user:
     ```
     ❌ This ticket is not a new rule request.
     
     Ticket type: {issue_type}
     Expected: Story
     
     This skill is only for implementing new validation rules (Story type).
     ```

3. **If validation passes**, proceed to present ticket information:
   - **Ticket**: [TICKET-NUMBER] Title
   - **Type**: Story
   - **Priority**: High/Medium/Low
   - **Description**: (formatted clearly)
   - **Acceptance Criteria**: (if present)

## Step 2: Git Workflow

**Follow the git workflow from implement-jira exactly:**

Reference: @.claude/skills/implement-jira.md (Step 2)

1. **Update main branch**:
   ```bash
   git checkout main
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create descriptive branch**:
   - Format: `TICKET-NUMBER_short_rule_description`
   - Example: `PDRIVE-553_check_disk_usage`
   
   ```bash
   git checkout -b PDRIVE-XXX-short-description
   git branch --show-current
   ```

**IMPORTANT**: Only proceed after confirming the branch is created and checked out.

## Step 3: Analyze Ticket for Rule Requirements

Extract from the ticket description and acceptance criteria:

1. **Rule name**: Determine the `unique_name` (e.g., `is_disk_space_sufficient`)
2. **Domain**: Identify which domain to use (hw, network, linux, storage, k8s, etcd, security) or create a new domain if none fit
3. **Rule type**: Determine if it's a `Rule` or `OrchestratorRule`
4. **Objective hosts**: Which nodes to run on (ALL_NODES, MASTERS, WORKERS, etc.)
5. **Validation logic**: What command(s) to run and what to check

Present this analysis to the user and ask for confirmation before proceeding.

## Step 4: Create the Rule

**Follow rule creation guidelines from:**
- @.claude/skills/new-rule.md
- @.claude/rules/in-cluster-check.md

### 4a. Create Rule Class

Place the rule in `src/in_cluster_checks/rules/<domain>/<file>.py`:

- Use appropriate rule type (Rule or OrchestratorRule)
- Set `objective_hosts`, `unique_name`, `title`
- Implement `run_rule()` returning `RuleResult`
- Add `is_prerequisite_fulfilled()` if needed
- **CRITICAL**: All commands MUST use `SafeCmdString`
- Add wiki link to `links` field (see Step 6 for wiki URL format)

**Important reminders:**
- NO use of `self.logger` - return messages via RuleResult
- Use `UnExpectedSystemOutput` for command failures
- Follow all guidelines from `.claude/rules/code-style.md`
- Place ALL imports at the top of the file

### 4b. Register in Domain

Add the rule to the domain in `src/in_cluster_checks/domains/<domain>.py`:

```python
from in_cluster_checks.rules.<domain>.<file> import NewRuleName

class SomeDomain(RuleDomain):
    def get_rule_classes(self) -> List[type]:
        return [
            # ... existing rules ...
            NewRuleName,
        ]
```

## Step 5: Write Tests

**Follow test guidelines from:**
- @.claude/skills/new-rule.md (Step 4)
- @.claude/rules/testing.md

Create tests in `tests/rules/<domain>/test_<file>.py`:

- Use `RuleTestBase` framework
- Define `scenario_passed` and `scenario_failed`
- Command strings MUST match exactly what the rule executes
- Use `CmdOutput` for mocking command results
- Update domain test file to include the new rule

**Run tests**:
```bash
source .venv/bin/activate
pytest tests/rules/<domain>/test_<file>.py -v
```

Ensure all tests pass before proceeding.

## Step 6: Create Wiki Page Content

**REQUIRED**: Every new rule MUST have wiki documentation.

**Reference**: @.claude/rules/in-cluster-check.md (Documentation section, lines 66-93)

### 6a. Fetch Wiki Template

Use WebFetch to read an existing wiki page as a template:
```
WebFetch(url="https://github.com/RedHatInsights/incluster-checks/wiki/Security-‐-TLS-certificate-expiry")
```

### 6b. Generate Wiki Content

Create wiki page content in **markdown format** following the standard structure:

**Wiki URL Format**: `https://github.com/RedHatInsights/incluster-checks/wiki/{Domain}-‐-{Rule-Title}`
- Use the rule's `title` field with spaces replaced by dashes
- Use `‐` (not `-`) in URLs due to GitHub wiki encoding
- Example: "Check kubelet CA certificate expiry" → `Security-‐-Check-kubelet-CA-certificate-expiry`

**Standard Wiki Structure**:
- **Description**: What the rule checks, why it's important, severity, failure thresholds
- **Prerequisites**: Required access, tools, or conditions
- **Impact**: What happens if the condition fails
- **Root Cause**: Common reasons for failure
- **Diagnostics**: Commands to investigate manually
- **Solution**: Step-by-step remediation with code examples
- **Resources**: Links to official docs, KCS articles, guides

### 6c. Present Wiki Content

Show the complete wiki page content in a markdown code block for easy copy-paste:

```
Here's the wiki page content for your new rule.

**IMPORTANT - Manual Steps Required:**

1. **Copy the wiki content** from the markdown code block below
2. **Navigate to**: https://github.com/RedHatInsights/incluster-checks/wiki/{Domain}-‐-{Rule-Title}
3. Click "Create new page"
4. Paste the content
5. Save the page
6. **Verify the wiki link** in your rule's `links` field matches the created wiki page URL

```markdown
[Wiki content here]
```

**Note**: GitHub wikis are not accessible via API, so this must be done manually. Make sure the wiki link in the rule code matches the actual wiki page URL after creation.
```

## Step 7: Run All Tests

Before committing, ensure everything works:

```bash
source .venv/bin/activate

# Run the new rule's tests
pytest tests/rules/<domain>/test_<file>.py -v

# Run all tests
pytest --cov=src/in_cluster_checks --cov-report=term-missing

# Run pre-commit checks
pre-commit run --all-files
```

All checks must pass before proceeding.

## Step 8: Ready to Commit?

**IMPORTANT**: Ask the user if they're ready to commit the changes.

Show summary:
- Rule class created: `src/in_cluster_checks/rules/<domain>/<file>.py`
- Tests created: `tests/rules/<domain>/test_<file>.py`
- Domain updated: `src/in_cluster_checks/domains/<domain>.py`
- All tests passing

Wait for user confirmation.

When committing:
- Use conventional commits format: `feat(TICKET-NUMBER): add <rule-title>`
- Follow commit attribution rules from `.claude/rules/git-workflow.md`
- Include ticket number in commit message

## Step 9: Ensure Latest Code

**Reference**: @.claude/skills/implement-jira.md (Step 7)

After committing, rebase on upstream:

```bash
git fetch upstream
git rebase upstream/main
```

Guide the user through any conflicts if they occur.

## Step 10: Push the Branch

```bash
git push -u origin <branch-name>
```

## Step 11: Create Pull Request

**Follow GitHub MCP guidelines from**: @.claude/rules/github-mcp.md

Use `mcp__plugin_github_github__create_pull_request`:

**CRITICAL - Get User Approval First**:
- Show the proposed PR title, body, head, base
- **MUST** wait for explicit user confirmation before creating

**PR Details**:
- **owner**: RedHatInsights
- **repo**: incluster-checks
- **head**: `<username>:<branch-name>` (user's fork branch)
- **base**: main
- **title**: `feat(TICKET-NUMBER): add <rule-title>`
- **body**:
  ```markdown
  ## Ticket
  https://redhat.atlassian.net/browse/<TICKET-NUMBER>
  
  ## Description
  [Ticket description]
  
  ## Changes
  - Created new validation rule: <rule-name>
  - Added tests with coverage
  - Registered in <domain> domain
  
  ## Testing
  - ✅ Unit tests pass
  - ✅ Pre-commit checks pass
  - ✅ Coverage maintained
  
  ## Wiki Documentation
  Wiki page URL: https://github.com/RedHatInsights/incluster-checks/wiki/{Domain}-‐-{Rule-Title}
  (Will be created after PR approval)
  ```

Return the PR URL to the user.

## Step 12: Update Jira Ticket (Optional)

Offer to update the Jira ticket with implementation details:

**MUST ask user for approval first** - Show what will be added:

```markdown
## Implementation Summary

Created new validation rule: `<unique_name>`

**Files Created/Updated:**
- `src/in_cluster_checks/rules/<domain>/<file>.py` - Rule implementation
- `tests/rules/<domain>/test_<file>.py` - Test coverage
- `src/in_cluster_checks/domains/<domain>.py` - Domain registration

**Pull Request:** [PR #NUMBER](PR-URL)

**Wiki Documentation:** [Rule Wiki Page](wiki-url)

**Status:** Ready for review
```

Use `mcp__plugin_atlassian_atlassian__addCommentToJiraIssue` with `contentFormat: "markdown"`.

## Error Handling

- **Invalid ticket number**: Inform user and exit
- **Wrong issue type**: Show error message (Step 1) and exit
- **Git operation failure**: Show error, suggest fixes (e.g., add upstream remote)
- **Branch already exists**: Ask if they want to switch to it or create different branch
- **Tests fail**: Show failures, help debug before allowing commit
- **Missing upstream remote**: Suggest `git remote add upstream https://github.com/RedHatInsights/incluster-checks.git`

## Checklist

Before marking complete, verify:

- [ ] Ticket type validated as "Story"
- [ ] Branch created with format: `TICKET-NUMBER-description`
- [ ] Rule class created with all required fields
- [ ] All commands use `SafeCmdString`
- [ ] No `self.logger` usage in rule
- [ ] Rule registered in domain
- [ ] Tests written with passed and failed scenarios
- [ ] All tests passing
- [ ] Pre-commit checks passing
- [ ] Wiki page content created and provided to user
- [ ] User instructed to manually create wiki page and copy content
- [ ] Wiki link added to rule's `links` field
- [ ] User reminded to verify wiki link matches actual wiki page URL
- [ ] Committed with conventional commit format
- [ ] Rebased on upstream/main
- [ ] Pushed to origin
- [ ] PR created (after user approval)
- [ ] Jira ticket updated (after user approval)

## Example Workflow

```
User: /implement-rule-from-jira PDRIVE-505

Expected flow:
1. Fetch PDRIVE-505 from Jira
2. Validate issue type is "Story" ✓
3. Update main and create branch: PDRIVE-505_network_connectivity_check
4. Show ticket details and ask for confirmation
5. Analyze ticket → determine it's a network rule for ALL_NODES
6. Create rule in src/in_cluster_checks/rules/network/
7. Register in NetworkValidationDomain
8. Create tests in tests/rules/network/
9. Generate wiki page content and provide to user
10. Run tests → all pass ✓
11. Commit with: feat(PDRIVE-505): add network connectivity validation
12. Rebase on upstream/main
13. Push to origin
14. Show proposed PR details → user approves → create PR
15. Offer to update Jira ticket → user approves → add comment with PR link
```
