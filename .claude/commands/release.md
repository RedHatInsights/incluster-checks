Create release notes and prepare for a new version release.

$ARGUMENTS

---

## Step 1: Review Changes

Review git history since last release to understand what changed:

```bash
git log v<last-version>..HEAD --oneline
git diff v<last-version>..HEAD --stat
```

## Step 2: Determine Version Bump

Follow semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes to API or core behavior
- **MINOR**: New features, backward-compatible
- **PATCH**: Bug fixes, documentation updates

## Step 3: Update Version

Update version in `pyproject.toml`:

```toml
[project]
version = "X.Y.Z"
```

## Step 4: Generate Release Notes

Create a summary of changes organized by category:

### Added
- New features and capabilities

### Changed
- Changes to existing functionality

### Fixed
- Bug fixes

### Deprecated
- Features marked for removal

### Removed
- Removed features

## Step 5: Update CHANGELOG.md

Add new section at the top:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- Feature 1
- Feature 2

### Changed
- Change 1

### Fixed
- Fix 1
```

## Step 6: Commit Version Changes

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to X.Y.Z"
```

## Step 7: Create Git Tag

```bash
git tag -a vX.Y.Z -m "Release version X.Y.Z"
git push origin main --tags
```

## Step 8: Create GitHub Release

1. Go to GitHub repository
2. Click "Releases" → "Draft a new release"
3. Select tag: vX.Y.Z
4. Title: "Release X.Y.Z"
5. Copy content from CHANGELOG.md for this version
6. Publish release

## Checklist

- [ ] Version updated in pyproject.toml
- [ ] CHANGELOG.md updated with new version section
- [ ] All tests passing (`pytest`)
- [ ] Pre-commit checks passing
- [ ] Version commit created
- [ ] Git tag created and pushed
- [ ] GitHub release created
- [ ] Documentation updated if needed
