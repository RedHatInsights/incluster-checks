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
