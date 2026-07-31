"""Test OcApiUtils argument validation."""

import pytest

from in_cluster_checks.utils.oc_api_utils import OcApiUtils


class MockOperator:
    """Mock operator for testing."""

    def _add_cmd_to_log(self, cmd):
        pass

    def get_host_ip(self):
        return "localhost"


class TestValidateArgsSafe:
    """Test _validate_args_safe() argument validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.oc_api = OcApiUtils(MockOperator())

    def test_exact_match_flags(self):
        """Test exact match flags are allowed."""
        assert self.oc_api._validate_args_safe(["-o"]) is True
        assert self.oc_api._validate_args_safe(["-n"]) is True
        assert self.oc_api._validate_args_safe(["-A"]) is True
        assert self.oc_api._validate_args_safe(["--no-headers"]) is True
        assert self.oc_api._validate_args_safe(["--all-namespaces"]) is True

    def test_prefix_patterns(self):
        """Test prefix patterns with validated values are allowed."""
        # --since - Time durations
        assert self.oc_api._validate_args_safe(["--since=1h"]) is True
        assert self.oc_api._validate_args_safe(["--since=30m"]) is True
        assert self.oc_api._validate_args_safe(["--since=2d"]) is True
        assert self.oc_api._validate_args_safe(["--since=45s"]) is True

        # --tail - Numeric line counts
        assert self.oc_api._validate_args_safe(["--tail=15"]) is True
        assert self.oc_api._validate_args_safe(["--tail=100"]) is True

        # --field-selector - Field selectors
        assert self.oc_api._validate_args_safe(["--field-selector=type=kubernetes.io/tls"]) is True
        assert self.oc_api._validate_args_safe(["--field-selector=status.phase=Running"]) is True

    def test_jsonpath_valid(self):
        """Test valid JSONPath expressions are allowed."""
        # Basic JSONPath
        assert self.oc_api._validate_args_safe(["jsonpath={.spec.version}"]) is True
        assert self.oc_api._validate_args_safe(["jsonpath={.metadata.name}"]) is True

        # JSONPath with arrays
        assert self.oc_api._validate_args_safe(["jsonpath={.items[*].metadata.name}"]) is True
        assert self.oc_api._validate_args_safe(["jsonpath={.items[0].spec.nodeName}"]) is True

        # JSONPath with nested paths
        assert self.oc_api._validate_args_safe(["jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}"]) is True

        # JSONPath with field names containing hyphens (legitimate use case)
        assert self.oc_api._validate_args_safe(["jsonpath={.my-field-name}"]) is True
        assert self.oc_api._validate_args_safe(["jsonpath={.metadata.annotations.k8s-io/app}"]) is True

        # JSONPath with range expressions (spaces are legitimate)
        assert self.oc_api._validate_args_safe(["jsonpath={range .items[*]}"]) is True
        assert self.oc_api._validate_args_safe(["jsonpath={.items[*].status.conditions[?(@.type=='Ready')].status}"]) is True

        # JSONPath with filters using parentheses
        assert self.oc_api._validate_args_safe(["jsonpath={.items[?(@.metadata.name=='pod-1')]}"]) is True

        # Empty JSONPath (technically valid in kubectl)
        assert self.oc_api._validate_args_safe(["jsonpath={}"]) is True

    def test_jsonpath_injection_attacks(self):
        """Test that JSONPath injection attacks are blocked."""
        # Flag injection via space-hyphen pattern
        assert self.oc_api._validate_args_safe(["jsonpath={.name} --kubeconfig=/evil"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name} -o wide"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name} --all-namespaces"]) is False

        # Command injection attempts
        assert self.oc_api._validate_args_safe(["jsonpath=; rm -rf /"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath=$(malicious)"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath=`whoami`"]) is False

        # Shell operators (pipe, redirect, etc.)
        assert self.oc_api._validate_args_safe(["jsonpath=| cat /etc/passwd"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name}|ls"]) is False

        # Invalid characters (shell operators)
        assert self.oc_api._validate_args_safe(["jsonpath={.name};"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name}&"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name}<"]) is False
        assert self.oc_api._validate_args_safe(["jsonpath={.name}>"]) is False
        # Note: backslash (\) is allowed - it's used for escaping in JSONPath

    def test_jsonpath_structural_validation(self):
        """Test JSONPath structural validation (balanced brackets)."""
        # Unbalanced brackets
        assert self.oc_api._validate_args_safe(["jsonpath={{.name}"]) is False  # Extra {
        assert self.oc_api._validate_args_safe(["jsonpath={.name}}"]) is False  # Extra }
        assert self.oc_api._validate_args_safe(["jsonpath={.items[[*]}"]) is False  # Extra [
        assert self.oc_api._validate_args_safe(["jsonpath={.items[*]]}"]) is False  # Extra ]
        assert self.oc_api._validate_args_safe(["jsonpath={(.name))"]) is False  # Extra (
        assert self.oc_api._validate_args_safe(["jsonpath={((.name)}"]) is False  # Extra (

        # Closing before opening (order violation)
        assert self.oc_api._validate_args_safe(["jsonpath=}.name{"]) is False  # } before {
        assert self.oc_api._validate_args_safe(["jsonpath=].items["]) is False  # ] before [
        assert self.oc_api._validate_args_safe(["jsonpath=).name("]) is False  # ) before (

        # Mixed unbalanced
        assert self.oc_api._validate_args_safe(["jsonpath={[.name}"]) is False  # Missing ]
        assert self.oc_api._validate_args_safe(["jsonpath={(.name]}"]) is False  # ( with ]

    def test_jsonpath_empty(self):
        """Test empty JSONPath is rejected."""
        assert self.oc_api._validate_args_safe(["jsonpath="]) is False  # Empty value after prefix

    def test_resource_names(self):
        """Test resource names are allowed."""
        # Simple resource names
        assert self.oc_api._validate_args_safe(["pod"]) is True
        assert self.oc_api._validate_args_safe(["deployment"]) is True
        assert self.oc_api._validate_args_safe(["node"]) is True

        # Resource with dot notation
        assert self.oc_api._validate_args_safe(["deployment.apps"]) is True
        assert self.oc_api._validate_args_safe(["clusteroperators.config.openshift.io"]) is True
        assert self.oc_api._validate_args_safe(["nodenetworkconfigurationpolicies.nmstate.io"]) is True

        # Resource with namespace/name
        assert self.oc_api._validate_args_safe(["default/my-pod"]) is True
        assert self.oc_api._validate_args_safe(["openshift-config/cluster"]) is True

        # Resource with hyphen
        assert self.oc_api._validate_args_safe(["my-deployment"]) is True
        assert self.oc_api._validate_args_safe(["cluster-name"]) is True

        # Resource with underscore
        assert self.oc_api._validate_args_safe(["my_secret"]) is True
        assert self.oc_api._validate_args_safe(["config_map_name"]) is True

        # Resource with colon (for namespaced resources)
        assert self.oc_api._validate_args_safe(["network.operator/cluster"]) is True

    def test_combined_args(self):
        """Test multiple arguments together (as in actual usage)."""
        # From: oc get csr -o json
        assert self.oc_api._validate_args_safe(["csr", "-o", "json"]) is True

        # From: oc get secret kube-root-ca.crt -n openshift-config -o json
        assert self.oc_api._validate_args_safe(["secret", "kube-root-ca.crt", "-n", "openshift-config", "-o", "json"]) is True

        # From: oc get daemonsets --all-namespaces -o json
        assert self.oc_api._validate_args_safe(["daemonsets", "--all-namespaces", "-o", "json"]) is True

        # From: oc get pod -A -o jsonpath={...}
        assert (
            self.oc_api._validate_args_safe(["pod", "-A", "-o", "jsonpath={.items[*].metadata.name}"]) is True
        )

        # From: oc logs -n openshift-storage pod-name --since=1h --tail=15
        assert (
            self.oc_api._validate_args_safe(["-n", "openshift-storage", "pod-name", "--since=1h", "--tail=15"]) is True
        )

        # From: oc adm top nodes --no-headers
        assert self.oc_api._validate_args_safe(["top", "nodes", "--no-headers"]) is True

    def test_unsafe_args(self):
        """Test that unsafe arguments are rejected."""
        # Command injection attempts
        assert self.oc_api._validate_args_safe(["; rm -rf /"]) is False
        assert self.oc_api._validate_args_safe(["$(malicious)"]) is False
        assert self.oc_api._validate_args_safe(["`whoami`"]) is False
        assert self.oc_api._validate_args_safe(["| cat /etc/passwd"]) is False

        # Invalid characters in resource names
        assert self.oc_api._validate_args_safe(["pod&"]) is False
        assert self.oc_api._validate_args_safe(["pod|"]) is False
        assert self.oc_api._validate_args_safe(["pod;"]) is False

        # Invalid prefix (no alphanumeric start for resource names)
        assert self.oc_api._validate_args_safe([".hidden"]) is False
        assert self.oc_api._validate_args_safe(["/absolute/path"]) is False
        assert self.oc_api._validate_args_safe(["-unknown-flag"]) is False

        # Unsafe values in prefix patterns (command injection after prefix)
        assert self.oc_api._validate_args_safe(["jsonpath=; rm -rf /"]) is False
        assert self.oc_api._validate_args_safe(["--since=1h; malicious"]) is False
        assert self.oc_api._validate_args_safe(["--tail=15 | cat /etc/passwd"]) is False
        assert self.oc_api._validate_args_safe(["--field-selector=$(malicious)"]) is False

        # Invalid formats for prefix patterns
        assert self.oc_api._validate_args_safe(["--since=invalid"]) is False  # Not a valid duration
        assert self.oc_api._validate_args_safe(["--tail=abc"]) is False  # Not numeric

    def test_all_existing_usages(self):
        """Test validation against all actual usages from the codebase."""
        # Security rules
        assert self.oc_api._validate_args_safe(["csr", "-o", "json"]) is True
        assert (
            self.oc_api._validate_args_safe(["secret", "kube-root-ca.crt", "-n", "openshift-config", "-o", "json"])
            is True
        )
        assert (
            self.oc_api._validate_args_safe(["secret", "--field-selector=type=kubernetes.io/tls", "-A", "-o", "json"])
            is True
        )

        # Network rules
        assert self.oc_api._validate_args_safe(["dns.operator.openshift.io/cluster", "-o", "json"]) is True
        assert self.oc_api._validate_args_safe(["pod", "-A", "-o", "jsonpath={}"]) is True
        assert (
            self.oc_api._validate_args_safe(["nodenetworkconfigurationpolicies.nmstate.io", "-A", "-o", "json"])
            is True
        )

        # Storage rules
        assert (
            self.oc_api._validate_args_safe(["pv", "-o", "jsonpath={.items[*].spec.csi.volumeAttributes.subvolumeName}"])
            is True
        )
        assert (
            self.oc_api._validate_args_safe(["-n", "openshift-storage", "pod-name", "--since=1h", "--tail=15"])
            is True
        )

        # K8s rules
        assert self.oc_api._validate_args_safe(["top", "nodes", "--no-headers"]) is True
        assert self.oc_api._validate_args_safe(["daemonsets", "--all-namespaces", "-o", "json"]) is True
        assert self.oc_api._validate_args_safe(["clusteroperators.config.openshift.io", "--no-headers"]) is True
        assert (
            self.oc_api._validate_args_safe(
                ["policies.policy.open-cluster-management.io", "--all-namespaces", "-o", "json"]
            )
            is True
        )
        assert (
            self.oc_api._validate_args_safe(["config.imageregistry.operator.openshift.io", "cluster", "-o", "json"])
            is True
        )
        assert self.oc_api._validate_args_safe(["clusteroperators", "-o", "json"]) is True
        assert self.oc_api._validate_args_safe(["console.operator.openshift.io", "cluster", "-o", "json"]) is True
        assert self.oc_api._validate_args_safe(["network.operator.openshift.io", "cluster", "-o", "json"]) is True
        assert self.oc_api._validate_args_safe(["csv", "-n", "open-cluster-management", "-o", "json"]) is True

        # Resources utilization
        assert self.oc_api._validate_args_safe(["node", "node-name"]) is True

    def test_field_selector_pattern(self):
        """Test that --field-selector= prefix pattern works."""
        # This should pass because --field-selector= is in our prefix_allowed list
        assert self.oc_api._validate_args_safe(["--field-selector=type=kubernetes.io/tls"]) is True
        assert self.oc_api._validate_args_safe(["--field-selector=status.phase=Running"]) is True

        # Combined with other flags
        assert self.oc_api._validate_args_safe(["secret", "-A", "-o", "json"]) is True
