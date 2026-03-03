# Examples

This directory contains examples demonstrating how to use the OpenShift In-Cluster Checks framework.

## Basic Examples

### 1. Basic Usage (`basic_usage.py`)

The simplest way to run in-cluster checks:

```python
from in_cluster_checks.runner import InClusterCheckRunner
from pathlib import Path

runner = InClusterCheckRunner()
runner.run(output_path=Path("./cluster-checks.json"))
```

**Run it:**
```bash
python examples/basic_usage.py
```

### 2. Custom Configuration (`custom_configuration.py`)

Shows how to customize the runner configuration:

```python
from in_cluster_checks.runner import InClusterCheckRunner

runner = InClusterCheckRunner(
    max_workers=75,
)
```

**Run it:**
```bash
python examples/custom_configuration.py
```

## Advanced Examples

### 3. Custom Rule (`custom_rule.py`)

Demonstrates how to create a custom validation rule:

- Define a new rule class inheriting from `Rule`
- Implement `set_document()` and `run_rule()` methods
- Run commands on nodes and parse output
- Return pass/fail results

**View it:**
```bash
cat examples/custom_rule.py
python examples/custom_rule.py
```

### 4. Custom Domain (`custom_domain.py`)

Shows how to create a custom domain with custom rules:

- Define a domain class inheriting from `RuleDomain`
- Group related rules together
- Integrate with the runner's domain discovery

**View it:**
```bash
cat examples/custom_domain.py
python examples/custom_domain.py
```

## Prerequisites

Before running these examples:

1. **Ensure you're logged into an OpenShift cluster:**
   ```bash
   oc login https://api.your-cluster.com:6443
   ```

2. **Install the package:**
   ```bash
   pip install in-cluster-checks
   ```

   Or install in development mode:
   ```bash
   pip install -e .
   ```

## Example Output

All examples that run checks will create a JSON output file containing:
- Rule execution results
- Node information
- Command outputs (with secrets filtered)
- Timestamps
- Pass/fail status

View the results:
```bash
cat cluster-checks.json | jq .
```

## Next Steps

- Read the [README](../README.md) for CLI usage
- See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines
- Check the main codebase for more rule and domain examples
