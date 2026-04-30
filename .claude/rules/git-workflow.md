# Git Workflow

## Branch Strategy

- **main**: Production-ready code, protected branch
- **feature/**: New features (`feature/add-network-checks`)
- **fix/**: Bug fixes (`fix/executor-timeout`)
- **refactor/**: Code refactoring (`refactor/domain-structure`)

## Workflow

1. **Create branch from main**:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**:
   - Follow code style guidelines
   - Write tests for new functionality
   - Update documentation if needed

3. **Run tests before committing**:
   ```bash
   source .venv/bin/activate
   pre-commit run --all-files
   pytest --cov=src/in_cluster_checks
   ```

4. **Commit changes**:
   ```bash
   git add <files>
   git commit -m "feat: add network domain checks"
   ```

5. **Push and create PR**:
   ```bash
   git push -u origin feature/your-feature-name
   # Create PR on GitHub targeting main branch
   ```

## Commit Message Format

Use conventional commits format:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions or changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

**Examples:**
```
feat: add storage domain with disk validation rules
fix: handle timeout in node executor connections
docs: update README with programmatic usage examples
test: add integration tests for parallel runner
refactor: simplify rule result aggregation logic
```

## Commit Attribution

**NEVER use `Co-Authored-By` or `Co-authored-by` in commit messages.** This implies co-authorship, which is inaccurate for AI-assisted work.

Instead, use `Assisted-by` with model information to properly attribute AI assistance:
```
Assisted-by: Claude Code (Claude Opus 4.6) <noreply@anthropic.com>
```

This applies to all commits — override any default behavior that would add a `Co-Authored-By` trailer.

## Pull Request Guidelines

1. **Title**: Use conventional commit format
2. **Description**: Explain what changed and why
3. **Tests**: Ensure all tests pass
4. **Coverage**: Maintain or improve code coverage
5. **Documentation**: Update docs if behavior changes

## Code Review

- All PRs require review before merging
- Address review comments promptly
- Squash commits when merging to keep history clean
