# OpenShift In-Cluster Checks - Open Source Plan

## Project Overview

This project provides a generic framework for running health validation rules directly on OpenShift cluster nodes using `oc debug`. It was extracted from Red Hat's Pendrive (insights-on-prem) project to benefit the broader OpenShift community.

## Extraction from Pendrive

### What Was Extracted

The core in-cluster check framework was successfully extracted from Pendrive, including:

- **Core Framework Components** (~3,305 lines of production code):
  - `Rule`: Base class for validation rules
  - `RuleDomain`: Orchestrator for groups of related rules
  - `NodeExecutor`: Execute commands on cluster nodes via `oc debug`
  - `NodeExecutorFactory`: Auto-discover nodes and create executors
  - `StructedPrinter`: JSON output formatting with secret filtering

- **Domain Implementations** (5 domains):
  - Hardware validation domain
  - Network validation domain
  - Linux validation domain
  - Storage validation domain
  - Hardware/Firmware details domain (informational collectors)

- **Rule Library** (12+ validation rules):
  - Disk usage checks
  - Memory validation
  - CPU governor validation
  - OVS network checks
  - SELinux validation
  - Systemd validation
  - And more...

- **Utilities and Interfaces**:
  - Secret filtering for sensitive data
  - Pluggable logger interface
  - Configuration management
  - Status and objective enums

### What Was Removed

All Pendrive-specific and confidential logic was removed:
- Pendrive flow orchestration (gather, scan, full-run)
- UI/menu components
- Must-gather processing
- HTML report generation (Pendrive-specific)
- Red Hat Insights integration
- Internal authentication/authorization
- Pendrive-specific configuration

The extracted framework is **100% generic** and contains no confidential Red Hat logic.

## Current Status

### ✅ Completed (as of extraction)

1. **Code Extraction**
   - Core framework successfully extracted
   - All Pendrive dependencies removed
   - Clean, standalone package structure

2. **Licensing**
   - GPL-3.0-or-later license applied
   - LICENSE file included
   - License declared in pyproject.toml

3. **Basic Documentation**
   - README with overview, features, architecture
   - Quick start examples
   - Custom rule creation guide

4. **Build Configuration**
   - pyproject.toml with package metadata
   - Dependencies: openshift-client, python-dateutil
   - Dev dependencies: pytest, pytest-cov, pre-commit, ruff

5. **Testing Infrastructure**
   - Test directory structure
   - pytest configuration
   - Coverage reporting setup

### ✅ Recently Added

6. **Command-Line Interface**
   - `openshift-checks` command via console script
   - Arguments: --log-level, --output, --debug-rule
   - List commands: --list-domains, --list-rules
   - Error handling with proper exit codes
   - Tested successfully on small lab cluster

7. **Pre-commit Hooks**
   - Code quality enforcement (black, flake8, isort)
   - Custom linter (no imports inside functions)
   - Automated testing with 80% coverage threshold
   - Adapted from insights-on-prem configuration

8. **Module Entry Point**
   - `python -m in_cluster_checks` support

9. **CI/CD Automation**
   - GitHub Actions workflow for automated testing
   - Pre-commit checks on Python 3.12
   - Tests on Python 3.12 and 3.13
   - Separate linting job (black, flake8, isort)
   - Codecov integration for coverage reports
   - Status badges in README

10. **Python 3.12+ Requirement**
   - Modern Python syntax support (PEP 604 union types)
   - Updated all classifiers and dependencies

## Roadmap

### Phase 1: PyPI Publication (Next Priority)

- [ ] Test package building: `python -m build`
- [ ] Verify installation from wheel
- [ ] Create PyPI account
- [ ] Publish to PyPI
- [ ] Update README with actual pip install instructions

### Phase 2: CI/CD Automation ✅ COMPLETED

- [x] GitHub Actions for testing:
  - Test on Python 3.12, 3.13
  - Run linting (black, flake8, isort)
  - Run tests with coverage
  - Upload coverage reports

- [ ] GitHub Actions for publishing:
  - Trigger on version tags (v*.*.*)
  - Build and publish to PyPI automatically

- [x] Add status badges to README

### Phase 3: Enhanced Features

- [ ] Configuration file support:
  - YAML/JSON config files
  - Default location: `~/.config/openshift-checks/config.yaml`
  - CLI override with `--config` flag

- [ ] Advanced filtering:
  - Domain selection (`--domains hw,network`)
  - Rule selection (`--rules check_disk_usage,check_memory`)
  - Node/role filtering

- [ ] Output enhancements:
  - Human-readable output format option
  - stdout vs file output selection
  - Result summary display

### Phase 4: Documentation & Examples

- [ ] Comprehensive documentation:
  - Detailed CLI usage guide
  - Configuration reference
  - Troubleshooting section
  - Real-world examples

- [ ] Examples directory:
  - `basic_usage.py` - Simple programmatic usage
  - `custom_rule.py` - Create custom validation rule
  - `custom_domain.py` - Create custom domain
  - `sample_config.yaml` - Sample configuration file

- [ ] Contributing guidelines:
  - How to add new rules
  - How to add new domains
  - Code style guidelines
  - Testing requirements
  - PR process

### Phase 5: Community Building

- [ ] Issue templates
- [ ] PR template
- [ ] CODE_OF_CONDUCT.md
- [ ] SECURITY.md for reporting security issues
- [ ] Discussion forum or mailing list

## Design Principles

The open source framework follows these principles:

1. **Generic & Reusable**: No organization-specific logic
2. **Extensible**: Easy to add new rules and domains
3. **Pluggable**: Interfaces for logging, configuration
4. **Production-Ready**: Comprehensive error handling and testing
5. **Well-Documented**: Clear documentation and examples
6. **Community-Friendly**: Open to contributions

## Success Criteria

The project will be considered production-ready when:

- ✅ Code is extracted and cleaned (DONE)
- ✅ License is applied (DONE)
- ✅ CLI is functional (DONE)
- ✅ Pre-commit hooks enforce quality (DONE)
- ⏳ Package is published to PyPI
- ⏳ CI/CD is automated
- ⏳ Documentation is comprehensive
- ⏳ Contributing guidelines are clear

## Repository Information

- **GitHub**: https://github.com/sprizend-rh/in-cluster-checks
- **Package Name**: `in-cluster-checks`
- **CLI Command**: `openshift-checks`
- **Python Module**: `in_cluster_checks`
- **License**: GPL-3.0-or-later

## Acknowledgments

This framework was extracted from Red Hat's Pendrive (insights-on-prem) project. The core validation infrastructure is generic and contains no confidential logic, making it suitable for open-source release to benefit the wider OpenShift community.

Special thanks to the Pendrive team for developing the original framework.
