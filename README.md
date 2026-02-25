# OpenShift In-Cluster Checks

A generic framework for running health validation rules directly on OpenShift cluster nodes using `oc debug`.

## Overview

This framework provides infrastructure for:
- Running validation rules on cluster nodes via `oc debug`
- Parallel execution of rules across multiple nodes
- Secret filtering and output formatting
- Prerequisite checking and domain orchestration
- Insights-compatible JSON output

Originally developed as part of Red Hat's Pendrive project, this framework has been extracted as open-source to benefit the broader OpenShift community.

## Features

- **Generic validation framework**: Base classes for creating custom health check rules
- **OpenShift integration**: Direct node access via `oc debug` with persistent connections
- **Domain organization**: Group related rules into domains (hardware, network, linux, storage)
- **Parallel execution**: Run rules concurrently across multiple nodes
- **Secret filtering**: Automatic redaction of sensitive data from outputs
- **Extensible**: Easy to add new rules and domains

## Installation

```bash
pip install openshift-in-cluster-checks
```

## Quick Start

First, ensure you're logged into your OpenShift cluster:

```bash
oc login https://api.your-cluster.com:6443
```

Then run the checks:

```bash
# Run all checks (output saved to ./cluster-checks.json)
openshift-checks --output ./cluster-checks.json

# Run with debug logging
openshift-checks --log-level DEBUG

# Debug a specific rule (disables secret filtering)
openshift-checks --debug-rule "check_disk_usage"

# List available domains
openshift-checks --list-domains

# List all available rules
openshift-checks --list-rules
```

## Programmatic Usage

You can also use the framework programmatically in your Python code:

```python
from openshift_in_cluster_checks.runner import InClusterCheckRunner
from openshift_in_cluster_checks.interfaces.config import InClusterCheckConfig
from pathlib import Path

# Configure runner
config = InClusterCheckConfig(
    debug_rule_flag=False,
    parallel_execution=True,
    max_workers=10,
    command_timeout=120,
)

runner = InClusterCheckRunner(config=config)

# Run checks and save results
output_path = Path("./results/cluster-checks.json")
runner.run(output_path=output_path)
```

## Architecture

### Core Components

- **Rule**: Base class for validation rules
- **RuleDomain**: Orchestrator for groups of related rules
- **Operator**: Command execution abstraction
- **NodeExecutor**: Execute commands on cluster nodes via `oc debug`
- **LoggerInterface**: Pluggable logging abstraction

### Built-in Domains

- **Hardware**: Disk usage, memory, CPU, temperature validation
- **Network**: OVS, DNS, bonding checks
- **Linux**: Systemd, SELinux, clock synchronization
- **Storage**: Storage validation rules
- **Hardware/Firmware Details**: Informational collectors for hardware inventory

## Creating Custom Rules

```python
from openshift_in_cluster_checks.core.rule import Rule
from openshift_in_cluster_checks.core.rule_result import RuleResult
from openshift_in_cluster_checks.utils.enums import Status, Objectives

class MyCustomRule(Rule):
    """Example custom validation rule."""

    objective_hosts = [Objectives.ALL_NODES]

    def set_document(self):
        self.unique_name = "my_custom_rule"
        self.title = "My Custom Validation Rule"

    def run_rule(self):
        # Run validation logic
        return_code, stdout, stderr = self.run_cmd("my-command")

        if return_code == 0:
            return RuleResult.passed("Validation passed")
        else:
            return RuleResult.failed(f"Validation failed: {stderr}")
```

## Requirements

- Python 3.9+
- OpenShift CLI (`oc`) installed and configured
- Access to OpenShift cluster

## Development

```bash
# Clone repository
git clone https://github.com/sprizend-rh/openshift-in-cluster-checks.git
cd openshift-in-cluster-checks

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run pre-commit checks
pre-commit run --all-files
```

## License

GNU General Public License v3.0 or later

See [LICENSE](LICENSE) for full text.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## Related Projects

- **Pendrive**: Red Hat's on-premise Insights validation tool (internal)
- **OpenShift**: Container orchestration platform

## Acknowledgments

This framework was extracted from Red Hat's Pendrive project. The core validation infrastructure is generic and contains no confidential logic, making it suitable for open-source release to benefit the wider OpenShift community.
