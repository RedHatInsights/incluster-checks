"""Unit tests for SecretFilter."""

import pytest

from in_cluster_checks.utils.secret_filter import SecretFilter


class TestSecretFilter:
    """Test SecretFilter regex patterns."""

    def test_jwt_token_redaction(self):
        """Test Kubernetes ServiceAccount JWT is redacted."""
        text = "eyJhbGciOiJSUzI1NiIsImtpZCI6IlJRQ.eyJpc3MiOiJrdWJlcm5ldGVz.signature"
        result = SecretFilter.sanitize(text)
        assert "eyJhbGci" not in result
        assert "REDACTED" in result

    def test_jwt_token_realistic_length(self):
        """Test JWT with realistic length is redacted."""
        jwt = "eyJhbGciOiJSUzI1NiIsImtpZCI6IlpXOG5jRW1qeEpLaUt2clRRVmFVOHVoLXBzWmYwcXdQZy1sZ3k5VEh4OGcifQ.eyJpc3MiOiJrdWJlcm5ldGVzL3NlcnZpY2VhY2NvdW50Iiwia3ViZXJuZXRlcy5pby9zZXJ2aWNlYWNjb3VudC9uYW1lc3BhY2UiOiJkZWZhdWx0In0.signature"
        result = SecretFilter.sanitize(jwt)
        assert jwt not in result
        assert "REDACTED" in result

    def test_openshift_session_token_redaction(self):
        """Test sha256~ OpenShift token is redacted."""
        token = "sha256~xJ9kL3mN2pQ4rS5tU6vW7xY8zA9bC0dE1fG2hH3iI4j"
        result = SecretFilter.sanitize(token)
        assert token not in result
        assert "REDACTED" in result

    def test_openshift_token_exact_43_chars(self):
        """Test OpenShift token with exactly 43 chars after tilde."""
        token = "sha256~" + "a" * 43
        result = SecretFilter.sanitize(token)
        assert token not in result
        assert "REDACTED" in result

    def test_ipmi_password_flag(self):
        """Test ipmitool -P flag password is redacted."""
        text = "ipmitool -U admin -P MyP@ssw0rd chassis status"
        result = SecretFilter.sanitize(text)
        assert "MyP@ssw0rd" not in result
        assert "REDACTED" in result

    def test_kubeconfig_cert_data_redaction(self):
        """Test kubeconfig certificate-data is redacted."""
        text = "client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t"
        result = SecretFilter.sanitize(text)
        assert "LS0tLS1CRU" not in result
        assert "REDACTED" in result

    def test_kubeconfig_key_data_redaction(self):
        """Test kubeconfig client-key-data is redacted."""
        text = "client-key-data: LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ=="
        result = SecretFilter.sanitize(text)
        assert "LS0tLS1CRU" not in result
        assert "REDACTED" in result

    def test_pem_private_key_single_line(self):
        """Test PEM private key block is redacted."""
        text = "-----BEGIN RSA PRIVATE KEY----- MIIEpAIBAAKCAQEA1234567890 -----END RSA PRIVATE KEY-----"
        result = SecretFilter.sanitize(text)
        assert "MIIEpAIBAAKCAQEA" not in result
        assert "REDACTED" in result

    def test_pem_private_key_multiline(self):
        """Test PEM private key multi-line block is redacted."""
        text = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890
xyzABCDEFGHIJKLMNOP1234567
-----END RSA PRIVATE KEY-----"""
        result = SecretFilter.sanitize(text)
        assert "MIIEpAIBAAKCAQEA" not in result
        assert "REDACTED" in result

    def test_pem_key_different_types(self):
        """Test different PEM key types are redacted."""
        for key_type in ["RSA", "EC", ""]:
            text = f"-----BEGIN {key_type} PRIVATE KEY----- data -----END {key_type} PRIVATE KEY-----".strip()
            result = SecretFilter.sanitize(text)
            assert "data" not in result
            assert "REDACTED" in result

    def test_case_insensitive_password(self):
        """Test --PASSWORD (uppercase) is redacted by regex."""
        text = "somecommand --PASSWORD=MySecret123"
        result = SecretFilter.sanitize(text)
        assert "MySecret123" not in result
        assert "REDACTED" in result

    def test_case_insensitive_bearer(self):
        """Test BEARER in uppercase is redacted."""
        text = " AUTHORIZATION: BEARER abc123def456"
        result = SecretFilter.sanitize(text)
        assert "abc123def456" not in result
        assert "REDACTED" in result

    def test_mixed_case_certificate_data(self):
        """Test mixed case certificate-data is redacted."""
        text = "Client-Certificate-Data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0t"
        result = SecretFilter.sanitize(text)
        assert "LS0tLS1CRU" not in result
        assert "REDACTED" in result

    def test_base64_decode_redaction(self):
        """Test base64 decode command is redacted."""
        text = "echo YWRtaW46cGFzc3dvcmQ= | base64 -d"
        result = SecretFilter.sanitize(text)
        assert "YWRtaW46cGFzc3dvcmQ=" not in result
        assert "REDACTED" in result

    def test_mysql_password_redaction(self):
        """Test MySQL password argument is redacted."""
        text = "mysql -u root -pMyPassword123 -h localhost"
        result = SecretFilter.sanitize(text)
        assert "MyPassword123" not in result
        assert "REDACTED" in result

    def test_mysql_password_with_special_chars(self):
        """Test MySQL password with special characters is fully redacted."""
        text = "mysql -u root -pMy$ecret -h localhost"
        result = SecretFilter.sanitize(text)
        assert "My$ecret" not in result
        assert "REDACTED" in result

    def test_bearer_token_redaction(self):
        """Test Bearer token in Authorization header is redacted."""
        text = " Authorization: Bearer abc123def456ghi789"
        result = SecretFilter.sanitize(text)
        assert "abc123def456ghi789" not in result
        assert "REDACTED" in result

    def test_bearer_token_with_dots(self):
        """Test Bearer token containing dots is fully redacted."""
        text = " Authorization: Bearer abc.def.ghi"
        result = SecretFilter.sanitize(text)
        assert "abc.def.ghi" not in result
        assert "REDACTED" in result

    def test_url_with_password_redaction(self):
        """Test URL with embedded password is redacted."""
        text = "https://admin:MySecret123@example.com/api"
        result = SecretFilter.sanitize(text)
        assert "MySecret123" not in result
        assert "REDACTED" in result

    def test_url_with_special_char_password(self):
        """Test URL with special characters in password is fully redacted."""
        text = "https://user1:My$ecret@example.com"
        result = SecretFilter.sanitize(text)
        assert "My$ecret" not in result
        assert "REDACTED" in result

    def test_redis_password_redaction(self):
        """Test Redis CLI password is redacted."""
        text = "redis-cli -h localhost -a 'MyRedisPass123'"
        result = SecretFilter.sanitize(text)
        assert "MyRedisPass123" not in result
        assert "REDACTED" in result

    def test_generic_password_flag_redaction(self):
        """Test generic --password flag is redacted."""
        text = "somecommand --password=MySecret123"
        result = SecretFilter.sanitize(text)
        assert "MySecret123" not in result
        assert "REDACTED" in result

    def test_generic_token_flag_with_dots(self):
        """Test --token flag with dotted value is fully redacted."""
        text = "somecommand --token abc.def"
        result = SecretFilter.sanitize(text)
        assert "abc.def" not in result
        assert "REDACTED" in result

    def test_none_input(self):
        """Test sanitize handles None input."""
        result = SecretFilter.sanitize(None)
        assert result is None

    def test_empty_string(self):
        """Test sanitize handles empty string."""
        result = SecretFilter.sanitize("")
        assert result == ""

    def test_list_of_strings(self):
        """Test sanitize handles list of strings."""
        text_list = [
            "normal text",
            "password=secret123",
            "another line",
        ]
        result = SecretFilter.sanitize(text_list)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == "normal text"
        assert result[1] == SecretFilter.REDACTED_MSG
        assert result[2] == "another line"

    def test_sha256_token_boundary_42_chars(self):
        """Test sha256~ with only 42 chars after tilde does not match."""
        token = "sha256~" + "a" * 42
        result = SecretFilter.sanitize(token)
        assert result == token

    def test_nested_list_input(self):
        """Test filter_string_array recurses into nested lists."""
        nested = [["password=secret123", "normal"], "another"]
        result = SecretFilter.sanitize(nested)
        assert isinstance(result, list)
        assert isinstance(result[0], list)
        assert result[0][0] == SecretFilter.REDACTED_MSG
        assert result[0][1] == "normal"
        assert result[1] == "another"

    def test_none_elements_in_list(self):
        """Test filter_string_array handles None elements in list."""
        result = SecretFilter.sanitize(["text", None, "more"])
        assert result == ["text", None, "more"]

    def test_standalone_non_secret_unchanged(self):
        """Test non-secret string passes through unchanged."""
        text = "oc get pods -n openshift-etcd"
        result = SecretFilter.sanitize(text)
        assert result == text

    def test_x_auth_token_redaction(self):
        """Test X-Auth-Token header value is redacted."""
        text = " X-Auth-Token:abc123secret456"
        result = SecretFilter.sanitize(text)
        assert "abc123secret456" not in result
        assert "REDACTED" in result

    def test_generic_secret_flag_redaction(self):
        """Test --secret flag value is redacted."""
        text = "somecommand --secret=MyTopSecret"
        result = SecretFilter.sanitize(text)
        assert "MyTopSecret" not in result
        assert "REDACTED" in result

    def test_multiple_secrets_in_one_string(self):
        """Test multiple secret types are all redacted in one string."""
        text = "mysql -u root -pMyPass123 --token=abc.def.ghi"
        result = SecretFilter.sanitize(text)
        assert "MyPass123" not in result
        assert "abc.def.ghi" not in result
        assert "REDACTED" in result

    def test_uppercase_bearer_in_filter_basic(self):
        """Test PASSWORD BEARER pattern is caught case-insensitively."""
        text = "password BEARER abc123"
        result = SecretFilter.sanitize(text)
        assert result == SecretFilter.REDACTED_MSG
