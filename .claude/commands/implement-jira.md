Fetch a Jira ticket, create a branch, and help implement it.

**Args**: Jira ticket number (e.g., PDRIVE-123)

# Implement Jira Ticket

You are helping the user implement a Jira ticket. Follow these steps in order:

## 1. Parse the Ticket Number
Extract the Jira ticket number from the args. Expected format: PDRIVE-XXX

## 2. Git Workflow - MUST DO FIRST
**CRITICAL**: Before doing ANY implementation work, complete these git steps:

### 2a. Update main branch
```bash
# Switch to main branch
git checkout main

# Fetch and rebase from upstream
git fetch upstream
git rebase upstream/main
```

### 2b. Fetch Jira Ticket Details (needed for branch name)
Fetch the ticket from Jira to get the title for the branch name:
- Use `mcp__plugin_atlassian_atlassian__getJiraIssue` with the ticket number
- Extract: title, description, acceptance criteria, issue type, priority, assignee

If needed, use GitHub MCP to:
- Check if a PR already exists for this ticket
- Review related branches or commits

### 2c. Create descriptive branch
Create a branch with a short descriptive name followed by the ticket number. Do NOT use directory-style prefixes like `feat/` or `fix/`.

**Format**: `<short-description>-<TICKET-NUMBER>`

**Examples**:
- `wiki-page-cmd-PDRIVE-553`
- `network-check-PDRIVE-505`
- `fix-timeout-PDRIVE-412`

```bash
# Create branch with descriptive name (no prefix, short, with ticket number)
git checkout -b <short-description>-<TICKET-NUMBER>

# Verify the branch was created correctly
git branch --show-current
```

**IMPORTANT**: Only proceed to step 3 after confirming the branch is created and checked out.

## 3. Present Ticket Information
Show the user a summary of the ticket (already fetched in step 2b):
- **Ticket**: [TICKET-NUMBER] Title
- **Type**: Bug/Task/Story
- **Priority**: High/Medium/Low
- **Description**: (formatted clearly)
- **Acceptance Criteria**: (if present)

## 4. Plan the Implementation
Based on the ticket details:
- Identify affected files and components
- Propose an implementation approach
- Ask for user confirmation before proceeding

## 5. Help with Implementation
- Implement the requested changes
- Follow all code style guidelines from `.claude/rules/code-style.md`
- Ensure proper testing based on `.claude/rules/testing.md`
- Run tests before committing: `source .venv/bin/activate && pytest`

## 6. Ready to Commit?
**IMPORTANT**: Before committing, ask the user if they're ready to commit the changes.
- Show summary of what was changed
- Wait for user confirmation
- When committing, use the conventional commits format from `.claude/rules/git-workflow.md`
- Include the ticket number in the commit message (e.g., `feat(PDRIVE-123): add new validation rule`)

## 7. Ensure Latest Code
After committing, ensure the branch is based on the latest upstream code:

```bash
# Fetch latest changes from upstream
git fetch upstream

# Rebase the branch on upstream/main
git rebase upstream/main
```

If conflicts occur, guide the user through resolving them.

## 8. Push the Branch
Push the branch to origin:

```bash
git push -u origin <branch-name>
```

## 9. Create Pull Request
Use GitHub MCP to offer creating a pull request:
- Follow all GitHub MCP guidelines from `.claude/rules/github-mcp.md`
- **MUST** show the user the proposed PR details and ask for explicit confirmation before creating
- Use the ticket title and description as PR title and description

**CRITICAL - Fork to Upstream PR**:
- Determine the fork by checking git remote origin URL
- **owner**: Your fork username (extracted from origin remote)
- **repo**: "incluster-checks"
- **head**: `<username>:<branch-name>` (your fork's branch)
- **base**: "main"
- **title**: Use conventional commit format with ticket number
- **body**: Include:
  - Ticket link: `https://redhat.atlassian.net/browse/<TICKET-NUMBER>`
  - Description from ticket
  - Key changes made
  - Testing performed
- Use `mcp__plugin_github_github__create_pull_request`
- Return the PR URL to the user

## 10. Update Jira Ticket (Optional)
After PR creation, offer to update the Jira ticket with implementation details:
- **MUST** ask the user for approval before updating the ticket
- Show the user what will be added to the ticket
- Add a comment with:
  - Brief summary of what was implemented
  - Key files created/updated
  - Any changes from the original task description (scope changes, additional features, etc.)
  - PR link formatted as `[PR #NUMBER](PR-URL)` for clickable link
- Use Atlassian MCP `mcp__plugin_atlassian_atlassian__addCommentToJiraIssue` with `contentFormat: "markdown"`

## Error Handling
- If the ticket number is invalid or not found, inform the user and exit
- If git operations fail (e.g., upstream remote doesn't exist), show the error and ask how to proceed
- If the branch already exists, ask the user if they want to switch to it or create a different branch
- If `upstream` remote is not configured, suggest adding it with: `git remote add upstream git@github.com:sprizend-rh/in-cluster-checks.git`

## Examples

User invokes: `/implement-jira PDRIVE-505`

Expected workflow:
1. Checkout main → fetch upstream → rebase upstream/main
2. Fetch ticket details from Jira (needed for branch name)
3. Create descriptive branch: `network-check-PDRIVE-505` (short description + ticket number, no prefix)
4. Show ticket summary
5. Plan implementation
6. Implement changes
7. Run tests: `source .venv/bin/activate && pytest`
8. Ask user if ready to commit
9. When confirmed, commit with conventional commit format: `feat(PDRIVE-505): description`
10. Fetch upstream and rebase on upstream/main to ensure latest code
11. Push branch to origin
12. Offer to create PR via GitHub MCP (following `.claude/rules/github-mcp.md` guidelines)
13. Offer to update Jira ticket with implementation summary and PR link (ask user approval first)
