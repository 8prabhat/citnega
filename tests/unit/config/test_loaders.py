"""Unit tests for config loaders."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from citnega.packages.config.loaders import _deep_merge, load_registry_toml, load_settings
from citnega.packages.config.settings import Settings


class TestLoadSettings:
    def test_defaults_loaded(self) -> None:
        settings = load_settings()
        assert settings.runtime.framework in ("adk", "langgraph", "crewai")
        assert settings.session.max_context_tokens == 8192

    def test_user_config_overrides_defaults(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.toml").write_text(
            '[runtime]\nframework = "crewai"\n'
        )
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


class TestDeepMerge:
    def test_flat_merge(self) -> None:
        base     = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        _deep_merge(base, override)
        assert base == {"a": 1, "b": 99, "c": 3}

    def test_nested_merge(self) -> None:
        base     = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 99}}
        _deep_merge(base, override)
        assert base == {"x": {"a": 1, "b": 99}}

    def test_non_dict_override_replaces(self) -> None:
        base     = {"x": {"a": 1}}
        override = {"x": "string"}
        _deep_merge(base, override)
        assert base["x"] == "string"
