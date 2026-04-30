# Release Process

This document describes how to create releases and publish to PyPI.

## Automatic PyPI Publishing

This repository uses **GitHub Trusted Publishing** to automatically publish to PyPI when you create a GitHub release.

### Setup (One-time)

1. **Configure PyPI Trusted Publisher** (do this before your first release):

   Go to PyPI and set up trusted publishing:
   - For **PyPI**: https://pypi.org/manage/account/publishing/
   - For **TestPyPI**: https://test.pypi.org/manage/account/publishing/

   Add a new publisher with these settings:
   - **PyPI Project Name**: `in-cluster-checks`
   - **Owner**: `RedHatInsights`
   - **Repository name**: `incluster-checks`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi` (for production) or `testpypi` (for test)

2. **Create GitHub Environments** (optional but recommended):

   Go to your repo Settings → Environments and create:
   - `pypi` environment (for production releases)
   - `testpypi` environment (for testing)

   You can add protection rules like requiring approval before publishing.

### Creating a Release

1. **Update version** in [pyproject.toml](pyproject.toml):
   ```toml
   [project]
   version = "0.2.0"  # Bump version
   ```

2. **Commit and push** the version change:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin main
   ```

3. **Create a Git tag**:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. **Create a GitHub Release**:
   - Go to: https://github.com/RedHatInsights/incluster-checks/releases/new
   - Choose the tag you just created (`v0.2.0`)
   - Title: `v0.2.0` or `Release 0.2.0`
   - Description: Add release notes (what's new, what changed)
   - Click "Publish release"

5. **Automatic publishing**:
   - GitHub Actions will automatically build and publish to both TestPyPI and PyPI
   - Monitor the workflow: https://github.com/RedHatInsights/incluster-checks/actions
   - Your package will be available at: https://pypi.org/project/in-cluster-checks/

## Manual Publishing (Fallback)

If you need to publish manually:

```bash
# Install tools
pip install --upgrade build twine

# Build the package
python -m build

# Upload to TestPyPI first (recommended)
python -m twine upload --repository testpypi dist/*

# Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ in-cluster-checks

# Upload to PyPI
python -m twine upload dist/*
```

### Skip SSL Verification (if needed)

If you encounter SSL certificate issues:

```bash
python -m twine upload --cert "" dist/*
```

## Versioning Strategy

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version (1.0.0): Incompatible API changes
- **MINOR** version (0.2.0): New functionality, backwards compatible
- **PATCH** version (0.1.1): Bug fixes, backwards compatible

### Version Examples

- `0.1.0` → `0.1.1`: Bug fix
- `0.1.1` → `0.2.0`: New feature (backwards compatible)
- `0.2.0` → `1.0.0`: Breaking changes or first stable release

## Pre-release Versions

For alpha/beta releases:

```toml
version = "0.2.0a1"  # Alpha
version = "0.2.0b1"  # Beta
version = "0.2.0rc1" # Release candidate
```

## Checklist Before Release

- [ ] All tests passing (`pytest`)
- [ ] Pre-commit hooks passing (`pre-commit run --all-files`)
- [ ] Version updated in `pyproject.toml`
- [ ] CHANGELOG updated (if you maintain one)
- [ ] Documentation updated
- [ ] Tested in a lab environment
- [ ] Git tag created and pushed
- [ ] GitHub release created

## Troubleshooting

### "Project already exists" on PyPI

You need to register the project name first. The first time you publish, PyPI will automatically create the project if the name is available.

### "Version already exists"

You cannot overwrite an existing version on PyPI. You must increment the version number.

### Trusted Publishing not working

Check:
1. Workflow name matches exactly: `publish.yml`
2. Environment name matches: `pypi` or `testpypi`
3. Repository settings are correct
4. The workflow has `id-token: write` permission

### SSL Certificate Errors

Use `--cert ""` flag to skip verification (see Manual Publishing section).

## Additional Resources

- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions for PyPI](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [Semantic Versioning](https://semver.org/)
- [Python Packaging Guide](https://packaging.python.org/)
