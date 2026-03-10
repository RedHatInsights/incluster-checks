# In-Cluster Checks

[![CI](https://github.com/sprizend-rh/in-cluster-checks/workflows/CI/badge.svg)](https://github.com/sprizend-rh/in-cluster-checks/actions)
[![codecov](https://codecov.io/gh/sprizend-rh/in-cluster-checks/branch/main/graph/badge.svg)](https://codecov.io/gh/sprizend-rh/in-cluster-checks) <!-- why unknown -->
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0) <!-- to update license -->
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

A generic framework for running health validation rules directly on OpenShift cluster nodes using `oc debug`.

## Key Advantages

- **Direct node access** - Rules run directly on cluster nodes via `oc debug`
- **Fast execution** - Parallel rule execution across multiple nodes
- **Relevant rules execution** - Only relevant rules run based on prerequisite checks
- **Easy debugging** - Full visibility into commands executed for each rule

<br>
Originally developed as part of Red Hat's Pendrive project, this framework has been extracted as open-source to benefit the broader OpenShift community.

Rules are organized by topic into domains (hardware, network, linux, storage).

## Installation

**Prerequisites:**
- Python >= 3.12
- pip (Python package installer)

### Connected Environment

**Install the framework:**
```bash
pip install in-cluster-checks
```

Or if `pip` is not found, use:
```bash
python3 -m pip install in-cluster-checks
```

### Disconnected Environment

For environments without internet access:

1. **Download the package** on a connected machine:
   ```bash
   pip download in-cluster-checks --dest ./packages
   # Or: python3 -m pip download in-cluster-checks --dest ./packages
   ```

2. **Transfer the packages** to the disconnected environment (copy the `./packages` directory)

3. **Install from local packages**:
   ```bash
   pip install --no-index --find-links=./packages in-cluster-checks
   # Or: python3 -m pip install --no-index --find-links=./packages in-cluster-checks
   ```

## Running in-cluster-checks

### Cluster Login
Ensure you're logged into your OpenShift cluster.

You can login by one of the following options:

#### Login with Username and Password:

Use the cluster API URL and your credentials.

```bash
oc login https://api.your-cluster.com:6443
```
#### Login Using a Kubeconfig File:

If you already have a kubeconfig file with credentials:
```bash
export KUBECONFIG=/path/to/kubeconfig
```

### Usage Examples
You can run in-cluster-checks with the following options:

```bash
# Run all checks. Use --output to save run results to ./cluster-checks.json
in-cluster-checks --output ./cluster-checks.json

# Run a specific rule (disables secret filtering)
in-cluster-checks --debug-rule "check_disk_usage"

# Run with debug logging
in-cluster-checks --log-level DEBUG
```

To see all available options, run:
```bash
in-cluster-checks --help
```


**Note:** To control execution performance, use `--max-workers` to set the maximum number of parallel workers (default: 50).




## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.
For more information about contribution, check out for CONTRIBUTING.md 
<!-- put CONTRIBUTING.md  as link -->

## Related Projects

- **Pendrive**: Red Hat's on-premise Insights validation tool (internal)
- **OpenShift**: Container orchestration platform

## Acknowledgments

This framework was extracted from Red Hat's Pendrive project. The core validation infrastructure is generic and contains no confidential logic, making it suitable for open-source release to benefit the wider OpenShift community.

## License
<!-- Update to BSD after pull -->
GNU General Public License v3.0 or later

See [LICENSE](LICENSE) for full text.