"""
Section 10 config key tests.

Covers:
  - RuntimeSettings.strict_framework_validation default + env override
  - ContextSettings.strict_handler_loading default + env override
  - ContextSettings.handler_timeout_ms default + env override
  - settings.toml defaults match Python defaults
"""

from __future__ import annotations


class TestRuntimeSettings:
    def test_strict_framework_validation_default_false(self) -> None:
        from citnega.packages.config.settings import RuntimeSettings

        s = RuntimeSettings()
        assert s.strict_framework_validation is False

    def test_strict_framework_validation_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_RUNTIME_STRICT_FRAMEWORK_VALIDATION", "true")
        from citnega.packages.config.settings import RuntimeSettings

        s = RuntimeSettings()
        assert s.strict_framework_validation is True

    def test_framework_default_is_adk(self) -> None:
        from citnega.packages.config.settings import RuntimeSettings

        s = RuntimeSettings()
        assert s.framework == "adk"


class TestContextSettings:
    def test_strict_handler_loading_default_false(self) -> None:
        from citnega.packages.config.settings import ContextSettings

        s = ContextSettings()
        assert s.strict_handler_loading is False

    def test_strict_handler_loading_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_CONTEXT_STRICT_HANDLER_LOADING", "true")
        from citnega.packages.config.settings import ContextSettings

        s = ContextSettings()
        assert s.strict_handler_loading is True

    def test_handler_timeout_ms_default_zero(self) -> None:
        from citnega.packages.config.settings import ContextSettings

        s = ContextSettings()
        assert s.handler_timeout_ms == 0

    def test_handler_timeout_ms_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_CONTEXT_HANDLER_TIMEOUT_MS", "500")
        from citnega.packages.config.settings import ContextSettings

        s = ContextSettings()
        assert s.handler_timeout_ms == 500

    def test_default_handlers_list(self) -> None:
        from citnega.packages.config.settings import ContextSettings

        s = ContextSettings()
        assert "recent_turns" in s.handlers
        assert "token_budget" in s.handlers


class TestPolicySettings:
    def test_policy_template_default_dev(self) -> None:
        from citnega.packages.config.settings import PolicySettings

        s = PolicySettings()
        assert s.template == "dev"

    def test_policy_template_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_POLICY_TEMPLATE", "locked_down")
        from citnega.packages.config.settings import PolicySettings

        s = PolicySettings()
        assert s.template == "locked_down"


class TestWorkspaceSettings:
    def test_onboarding_manifest_path_default(self) -> None:
        from citnega.packages.config.settings import WorkspaceSettings

        s = WorkspaceSettings()
        assert s.onboarding_manifest_path == ".citnega/bundle_manifest.json"

    def test_onboarding_require_signature_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_WORKSPACE_ONBOARDING_REQUIRE_SIGNATURE", "true")
        from citnega.packages.config.settings import WorkspaceSettings

        s = WorkspaceSettings()
        assert s.onboarding_require_signature is True


class TestRemoteSettings:
    def test_remote_defaults(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        s = RemoteExecutionSettings()
        assert s.enabled is False
        assert s.worker_mode == "inprocess"
        assert s.require_signed_envelopes is True
        assert s.envelope_signing_key_id == "current"
        assert s.envelope_verification_keys == []
        assert s.http_endpoint == ""
        assert s.request_timeout_ms == 15000
        assert s.verify_tls is True
        assert s.ca_cert_path == ""
        assert s.client_cert_path == ""
        assert s.client_key_path == ""
        assert s.service_host == "127.0.0.1"
        assert s.service_port == 8787
        assert s.service_isolation_profile == "process"
        assert s.service_container_runtime == "docker"
        assert s.service_container_image == ""
        assert s.service_container_name == ""
        assert s.service_tls_cert_path == ""
        assert s.service_tls_key_path == ""
        assert s.service_tls_client_ca_path == ""
        assert s.service_tls_require_client_cert is False

    def test_remote_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CITNEGA_REMOTE_ENABLED", "true")
        monkeypatch.setenv("CITNEGA_REMOTE_WORKERS", "4")
        monkeypatch.setenv("CITNEGA_REMOTE_WORKER_MODE", "http")
        monkeypatch.setenv("CITNEGA_REMOTE_HTTP_ENDPOINT", "http://127.0.0.1:9000/invoke")
        monkeypatch.setenv("CITNEGA_REMOTE_REQUEST_TIMEOUT_MS", "4500")
        monkeypatch.setenv("CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID", "2026-04")
        monkeypatch.setenv(
            "CITNEGA_REMOTE_ENVELOPE_VERIFICATION_KEYS",
            '["2026-03=old-secret","2026-04=new-secret"]',
        )
        monkeypatch.setenv("CITNEGA_REMOTE_CA_CERT_PATH", "/tmp/ca.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_CLIENT_CERT_PATH", "/tmp/client-cert.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_CLIENT_KEY_PATH", "/tmp/client-key.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_PORT", "9999")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_ISOLATION_PROFILE", "container")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_CONTAINER_RUNTIME", "podman")
        monkeypatch.setenv(
            "CITNEGA_REMOTE_SERVICE_CONTAINER_IMAGE",
            "ghcr.io/acme/citnega:latest",
        )
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_CONTAINER_NAME", "citnega-worker")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_TLS_CERT_PATH", "/tmp/server-cert.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_TLS_KEY_PATH", "/tmp/server-key.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_TLS_CLIENT_CA_PATH", "/tmp/ca.pem")
        monkeypatch.setenv("CITNEGA_REMOTE_SERVICE_TLS_REQUIRE_CLIENT_CERT", "true")
        from citnega.packages.config.settings import RemoteExecutionSettings

        s = RemoteExecutionSettings()
        assert s.enabled is True
        assert s.workers == 4
        assert s.worker_mode == "http"
        assert s.http_endpoint == "http://127.0.0.1:9000/invoke"
        assert s.request_timeout_ms == 4500
        assert s.envelope_signing_key_id == "2026-04"
        assert s.envelope_verification_keys == ["2026-03=old-secret", "2026-04=new-secret"]
        assert s.ca_cert_path == "/tmp/ca.pem"
        assert s.client_cert_path == "/tmp/client-cert.pem"
        assert s.client_key_path == "/tmp/client-key.pem"
        assert s.service_port == 9999
        assert s.service_isolation_profile == "container"
        assert s.service_container_runtime == "podman"
        assert s.service_container_image == "ghcr.io/acme/citnega:latest"
        assert s.service_container_name == "citnega-worker"
        assert s.service_tls_cert_path == "/tmp/server-cert.pem"
        assert s.service_tls_key_path == "/tmp/server-key.pem"
        assert s.service_tls_client_ca_path == "/tmp/ca.pem"
        assert s.service_tls_require_client_cert is True
