# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

In-Cluster Checks is a generic open-source framework for running health check rules directly on OpenShift cluster nodes using `oc debug`. Originally extracted from Red Hat's internal Pendrive project, this framework provides infrastructure for parallel rule execution, prerequisite checking, and Insights-compatible JSON output.

**Key Features:**
- Generic framework with base classes for custom health check rules
- OpenShift integration via `oc debug` with persistent connections
- Domain-based organization (hw, network, linux, storage, k8s, etcd, security, hw_fw_details)
- Parallel execution across multiple nodes
- Secret filtering for sensitive data
- Extensible architecture for custom rules and domains

## Test

```bash
source .venv/bin/activate           # ALWAYS activate venv first
pytest                              # Run unit tests
pytest --cov=src/in_cluster_checks --cov-report=term-missing  # With coverage
pre-commit run --all-files          # Code quality checks
```

## Key Environment Variables
- `KUBECONFIG`: Path to kubeconfig file for cluster access
- `OC_DEBUG_IMAGE`: Custom debug container image (optional)
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

## Dependencies

### Python Environment
- Python 3.12+ with virtual environment
- Key packages: pytest, pre-commit, coverage
- See `pyproject.toml` for full dependency list

## Development Workflow

1. **Create feature branch**: `git checkout -b feature/your-feature-name`
2. **Make changes**: Follow code style guidelines
3. **Run tests**: `source .venv/bin/activate && pytest`
4. **Pre-commit checks**: `pre-commit run --all-files`
5. **Commit changes**: Use conventional commits format
6. **Open PR**: Target `main` branch

## CLI Usage

```bash
# Run all checks (output saved to ./cluster-checks.json)
in-cluster-checks --output ./cluster-checks.json

# Run with debug logging
in-cluster-checks --log-level DEBUG

# Debug a specific rule (disables secret filtering)
in-cluster-checks --debug-rule "is_disk_space_sufficient"

# List available domains
in-cluster-checks --list-domains

# List all available rules
in-cluster-checks --list-rules
```

## Architecture

The framework is built around these core components:
- `src/in_cluster_checks/core/`: Base classes — Rule, RuleDomain, Operator, executors
- `src/in_cluster_checks/rules/`: Rule implementations by domain (hw, network, linux, storage)
- `src/in_cluster_checks/domains/`: Domain orchestrators that group related rules
- `src/in_cluster_checks/runner.py`: Main runner that discovers domains and coordinates execution
- `src/in_cluster_checks/cli.py`: Command-line interface entry point

See [@.claude/rules/in-cluster-check.md](rules/in-cluster-check.md) for detailed architecture documentation.

## Additional Resources

- **Project Wiki**: https://github.com/sprizend-rh/in-cluster-checks/wiki - Detailed knowledge sharing about rules and documentation
- **Contributing Guide**: See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup and contribution guidelines
