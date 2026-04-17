"""Unit tests for config loaders."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from citnega.packages.config.loaders import (
    _deep_merge,
    load_registry_toml,
    load_settings,
    validate_settings,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestLoadSettings:
    def test_defaults_loaded(self) -> None:
        settings = load_settings()
        assert settings.runtime.framework in ("adk", "langgraph", "crewai")
        assert settings.session.max_context_tokens == 8192

    def test_user_config_overrides_defaults(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.toml").write_text('[runtime]\nframework = "crewai"\n')
        settings = load_settings(app_home=tmp_path)
        assert settings.runtime.framework == "crewai"

    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CITNEGA_RUNTIME__MAX_CALLABLE_DEPTH", "5")
        settings = load_settings()
        assert settings.runtime.max_callable_depth == 5

    def test_missing_user_config_falls_back_to_defaults(self, tmp_path: Path) -> None:
        # No config/settings.toml in tmp_path
        settings = load_settings(app_home=tmp_path)
        assert settings.session.approval_timeout_seconds == 300

    def test_invalid_toml_raises(self, tmp_path: Path) -> None:
        from citnega.packages.shared.errors import InvalidConfigError

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.toml").write_text("not valid toml = [[[")
        with pytest.raises(InvalidConfigError):
            load_settings(app_home=tmp_path)


class TestLoadRegistryToml:
    def test_model_registry_has_models(self) -> None:
        data = load_registry_toml("model_registry")
        assert "models" in data
        assert len(data["models"]) >= 1

    def test_agent_registry_has_agents(self) -> None:
        data = load_registry_toml("agent_registry")
        assert "core_agents" in data
        assert "specialist_agents" in data

    def test_tool_registry_has_tools(self) -> None:
        data = load_registry_toml("tool_registry")
        assert "tools" in data
        assert any(t["name"] == "web_search" for t in data["tools"])


class TestValidateSettings:
    def _make_settings(self, **overrides):
        """Build a minimal valid Settings with optional field overrides."""
        from citnega.packages.config.settings import (
            ContextSettings,
            LoggingSettings,
            RuntimeSettings,
            Settings,
        )

        kwargs = {
            "runtime": RuntimeSettings(framework="stub"),
            "logging": LoggingSettings(level="INFO"),
            "context": ContextSettings(handlers=["recent_turns"]),
        }
        kwargs.update(overrides)
        return Settings(**kwargs)

    def test_valid_settings_returns_no_errors(self) -> None:
        settings = self._make_settings()
        errors = validate_settings(settings)
        assert errors == []

    def test_invalid_framework_reported(self) -> None:
        from citnega.packages.config.settings import RuntimeSettings

        settings = self._make_settings(runtime=RuntimeSettings(framework="unknown_fw"))
        errors = validate_settings(settings)
        assert any("[runtime] framework" in e for e in errors)

    def test_invalid_handler_reported(self) -> None:
        from citnega.packages.config.settings import ContextSettings

        settings = self._make_settings(
            context=ContextSettings(handlers=["recent_turns", "bogus_handler"])
        )
        errors = validate_settings(settings)
        assert any("bogus_handler" in e for e in errors)

    def test_invalid_log_level_reported(self) -> None:
        from citnega.packages.config.settings import LoggingSettings

        settings = self._make_settings(logging=LoggingSettings(level="VERBOSE"))
        errors = validate_settings(settings)
        assert any("[logging] level" in e for e in errors)

    def test_unknown_toml_section_reported(self) -> None:
        settings = self._make_settings()
        raw_toml = {"runtime": {}, "typo_section": {}}
        errors = validate_settings(settings, raw_toml=raw_toml)
        assert any("typo_section" in e for e in errors)

    def test_known_toml_sections_not_reported(self) -> None:
        settings = self._make_settings()
        raw_toml = {k: {} for k in ("runtime", "session", "logging", "workspace", "policy")}
        errors = validate_settings(settings, raw_toml=raw_toml)
        assert errors == []

    def test_multiple_errors_all_reported(self) -> None:
        from citnega.packages.config.settings import (
            ContextSettings,
            LoggingSettings,
            PolicySettings,
            RuntimeSettings,
        )

        settings = self._make_settings(
            runtime=RuntimeSettings(framework="bad_fw"),
            logging=LoggingSettings(level="NOPE"),
            context=ContextSettings(handlers=["unknown_h"]),
            policy=PolicySettings(template="invalid-template"),
        )
        errors = validate_settings(settings)
        assert len(errors) == 4

    def test_invalid_policy_template_reported(self) -> None:
        from citnega.packages.config.settings import PolicySettings

        settings = self._make_settings(policy=PolicySettings(template="corp"))
        errors = validate_settings(settings)
        assert any("[policy] template" in e for e in errors)

    def test_workspace_signature_requires_manifest(self) -> None:
        from citnega.packages.config.settings import WorkspaceSettings

        settings = self._make_settings(
            workspace=WorkspaceSettings(
                onboarding_require_manifest=False,
                onboarding_require_signature=True,
                onboarding_signature_key="secret",
            )
        )
        errors = validate_settings(settings)
        assert any("onboarding_require_signature=true requires onboarding_require_manifest=true" in e for e in errors)

    def test_workspace_signature_requires_key(self) -> None:
        from citnega.packages.config.settings import WorkspaceSettings

        settings = self._make_settings(
            workspace=WorkspaceSettings(
                onboarding_require_manifest=True,
                onboarding_require_signature=True,
                onboarding_signature_key="",
            )
        )
        errors = validate_settings(settings)
        assert any("onboarding_signature_key" in e for e in errors)

    def test_workspace_manifest_path_must_be_non_empty(self) -> None:
        from citnega.packages.config.settings import WorkspaceSettings

        settings = self._make_settings(
            workspace=WorkspaceSettings(onboarding_manifest_path="")
        )
        errors = validate_settings(settings)
        assert any("onboarding_manifest_path" in e for e in errors)

    def test_remote_enabled_signed_envelope_requires_key(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                enabled=True,
                require_signed_envelopes=True,
                envelope_signing_key="",
            )
        )
        errors = validate_settings(settings)
        assert any("envelope_signing_key" in e for e in errors)

    def test_remote_worker_mode_validation(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(remote=RemoteExecutionSettings(worker_mode="ssh"))
        errors = validate_settings(settings)
        assert any("[remote] worker_mode" in e for e in errors)

    def test_remote_http_mode_requires_endpoint(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                worker_mode="http",
                http_endpoint="",
                request_timeout_ms=1000,
            )
        )
        errors = validate_settings(settings)
        assert any("worker_mode='http' requires non-empty remote.http_endpoint" in e for e in errors)

    def test_remote_http_mode_rejects_invalid_endpoint(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                worker_mode="http",
                http_endpoint="localhost:9000/invoke",
                request_timeout_ms=1000,
            )
        )
        errors = validate_settings(settings)
        assert any("Expected absolute http(s) URL" in e for e in errors)

    def test_remote_http_mode_with_valid_endpoint_passes(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                worker_mode="http",
                http_endpoint="https://remote.example.com/invoke",
                request_timeout_ms=1000,
            )
        )
        errors = validate_settings(settings)
        assert not any("[remote]" in e for e in errors)

    def test_remote_verification_keys_reject_invalid_entry(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                envelope_signing_key="secret",
                envelope_signing_key_id="2026-04",
                envelope_verification_keys=["broken-entry"],
            )
        )
        errors = validate_settings(settings)
        assert any("envelope_verification_keys entries must use the format" in e for e in errors)

    def test_remote_container_profile_requires_image(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                service_isolation_profile="container",
                service_container_runtime="docker",
                service_container_image="",
            )
        )
        errors = validate_settings(settings)
        assert any("service_container_image" in e for e in errors)

    def test_remote_mtls_requires_client_cert_and_key_pair(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                client_cert_path="/tmp/client.pem",
                client_key_path="",
            )
        )
        errors = validate_settings(settings)
        assert any("client_cert_path and client_key_path" in e for e in errors)

    def test_remote_service_mtls_requires_client_ca(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                service_tls_cert_path="/tmp/server-cert.pem",
                service_tls_key_path="/tmp/server-key.pem",
                service_tls_require_client_cert=True,
                service_tls_client_ca_path="",
            )
        )
        errors = validate_settings(settings)
        assert any("service_tls_require_client_cert=true requires" in e for e in errors)

    def test_remote_service_tls_cert_and_key_must_be_paired(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                service_tls_cert_path="/tmp/server-cert.pem",
                service_tls_key_path="",
            )
        )
        errors = validate_settings(settings)
        assert any("service_tls_cert_path and service_tls_key_path" in e for e in errors)

    def test_remote_rotated_key_config_passes(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                enabled=True,
                worker_mode="http",
                http_endpoint="https://remote.example.com/invoke",
                envelope_signing_key="secret-new",
                envelope_signing_key_id="2026-04",
                envelope_verification_keys=["2026-03=secret-old", "2026-04=secret-new"],
                request_timeout_ms=1000,
            )
        )
        errors = validate_settings(settings)
        assert not any("[remote]" in e for e in errors)

    def test_remote_https_mtls_config_passes(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(
                worker_mode="http",
                http_endpoint="https://remote.example.com/invoke",
                request_timeout_ms=1000,
                ca_cert_path="/tmp/ca.pem",
                client_cert_path="/tmp/client-cert.pem",
                client_key_path="/tmp/client-key.pem",
                service_tls_cert_path="/tmp/server-cert.pem",
                service_tls_key_path="/tmp/server-key.pem",
                service_tls_client_ca_path="/tmp/ca.pem",
                service_tls_require_client_cert=True,
            )
        )
        errors = validate_settings(settings)
        assert not any("[remote]" in e for e in errors)

    def test_remote_request_timeout_ms_validation(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(request_timeout_ms=0)
        )
        errors = validate_settings(settings)
        assert any("request_timeout_ms" in e for e in errors)

    def test_remote_service_port_validation(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(service_port=70000)
        )
        errors = validate_settings(settings)
        assert any("service_port" in e for e in errors)

    def test_remote_service_isolation_profile_validation(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(service_isolation_profile="vm")
        )
        errors = validate_settings(settings)
        assert any("service_isolation_profile" in e for e in errors)

    def test_remote_service_host_must_be_non_empty(self) -> None:
        from citnega.packages.config.settings import RemoteExecutionSettings

        settings = self._make_settings(
            remote=RemoteExecutionSettings(service_host="")
        )
        errors = validate_settings(settings)
        assert any("service_host" in e for e in errors)

    def test_out_raw_populated_by_load_settings(self, tmp_path) -> None:
        """load_settings(_out_raw=...) must populate the dict with merged TOML."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.toml").write_text('[runtime]\nframework = "stub"\n')
        raw: dict = {}
        load_settings(app_home=tmp_path, _out_raw=raw)
        assert "runtime" in raw
        assert raw["runtime"].get("framework") == "stub"


class TestDeepMerge:
    def test_flat_merge(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self) -> None:
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 99}}
        _deep_merge(base, override)
        assert base == {"x": {"a": 1, "b": 99}}

    def test_non_dict_override_replaces(self) -> None:
        base = {"x": {"a": 1}}
        override = {"x": "string"}
        _deep_merge(base, override)
        assert base["x"] == "string"
