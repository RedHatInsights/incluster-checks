# GitHub MCP Integration

This project uses the GitHub MCP (Model Context Protocol) plugin for GitHub operations.

## When to Use GitHub MCP

**ALWAYS use GitHub MCP tools for GitHub operations** instead of the `gh` CLI or GitHub API directly:

- Listing pull requests, issues, branches
- Reading PR details, comments, reviews
- Creating/updating pull requests and issues
- Searching code, repositories, or issues
- Managing branches and commits
- Reading file contents from GitHub

## Available GitHub MCP Tools

### Pull Requests
- `mcp__plugin_github_github__list_pull_requests` - List PRs (filtered by state, base, head, etc.)
- `mcp__plugin_github_github__pull_request_read` - Get detailed PR information
- `mcp__plugin_github_github__create_pull_request` - Create new PR
- `mcp__plugin_github_github__update_pull_request` - Update existing PR
- `mcp__plugin_github_github__merge_pull_request` - Merge a PR
- `mcp__plugin_github_github__search_pull_requests` - Search PRs (use when filtering by author)

### Issues
- `mcp__plugin_github_github__list_issues` - List issues
- `mcp__plugin_github_github__issue_read` - Get detailed issue information
- `mcp__plugin_github_github__issue_write` - Create or update issues
- `mcp__plugin_github_github__add_issue_comment` - Add comment to issue
- `mcp__plugin_github_github__search_issues` - Search issues

### Code & Repository
- `mcp__plugin_github_github__get_file_contents` - Read file from GitHub
- `mcp__plugin_github_github__search_code` - Search code across repositories
- `mcp__plugin_github_github__list_commits` - List commits
- `mcp__plugin_github_github__get_commit` - Get commit details
- `mcp__plugin_github_github__list_branches` - List branches
- `mcp__plugin_github_github__create_branch` - Create new branch

### Reviews
- `mcp__plugin_github_github__pull_request_review_write` - Submit PR review
- `mcp__plugin_github_github__add_comment_to_pending_review` - Add review comment
- `mcp__plugin_github_github__add_reply_to_pull_request_comment` - Reply to comment

## Repository Information

- **Main repository**: `RedHatInsights/incluster-checks`

When using GitHub MCP tools, determine the owner/repo dynamically from git remotes:
```bash
# Get origin owner/repo from git remote URL
git remote get-url origin
# Get upstream owner/repo
git remote get-url upstream
```

For this project's upstream: `owner: "RedHatInsights"`, `repo: "incluster-checks"`

## Common Usage Patterns

### List open PRs in upstream
```
mcp__plugin_github_github__list_pull_requests(
  owner: "RedHatInsights",
  repo: "incluster-checks",
  state: "open"
)
```

### Get PR details
```
mcp__plugin_github_github__pull_request_read(
  owner: "RedHatInsights",
  repo: "incluster-checks",
  pull_number: 50
)
```

### Search for PRs by author
```
mcp__plugin_github_github__search_pull_requests(
  query: "is:pr author:USERNAME repo:RedHatInsights/incluster-checks"
)
```

### Create a pull request
```
mcp__plugin_github_github__create_pull_request(
  owner: "RedHatInsights",
  repo: "incluster-checks",
  title: "feat: add new validation rule",
  body: "Description of changes...",
  head: "YOUR-FORK:feature-branch",
  base: "main"
)
```

## Setup Requirements

The GitHub MCP requires a GitHub Personal Access Token set as an environment variable:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"
```

Token should have these scopes:
- `repo` - Full control of private repositories
- `read:org` - Read org and team membership
- `read:user` - Read user profile data
- `user:email` - Access user email addresses

## Best Practices

1. **Use load tools first**: Call `ToolSearch` to load GitHub MCP tools before using them
2. **Get repo context**: Use `git remote get-url origin` to determine owner/repo dynamically
3. **Check both fork and upstream**: When listing PRs/issues, check the upstream repo
4. **Paginate large results**: Use `perPage` and `page` parameters for large result sets
5. **Sort results**: Use `sort` and `direction` parameters to get most recent items first
