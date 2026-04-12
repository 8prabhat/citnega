"""
TOML config loading with precedence.

Precedence (lowest → highest):
  1. Bundled defaults (packages/config/defaults/*.toml)
  2. User config file (<app_home>/config/settings.toml)
  3. Profile file     (<app_home>/config/profiles/<profile>/settings.toml)
  4. Environment variables (CITNEGA_*)

The five registry/rules TOML files (model_registry, agent_registry,
tool_registry, routing_rules) are loaded separately as plain dicts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from citnega.packages.config.settings import Settings
from citnega.packages.shared.errors import InvalidConfigError

# Path to the bundled defaults directory
_DEFAULTS_DIR = Path(__file__).parent / "defaults"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file and return it as a dict. Requires Python 3.11+."""
    try:
        import tomllib  # stdlib since 3.11

        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise InvalidConfigError(f"Failed to parse TOML at {path}: {exc}", original=exc) from exc


def load_settings(
    app_home: Path | None = None,
    profile: str | None = None,
) -> Settings:
    """
    Load and merge all settings into a single validated Settings object.

    Args:
        app_home: Override the app home directory (useful in tests).
        profile:  Profile name (e.g. "dev"). Loaded from
                  <app_home>/config/profiles/<profile>/settings.toml.
    """
    # Resolve app_home: env var → explicit arg → None (PathResolver will set later)
    if app_home is None:
        env_home = os.environ.get("CITNEGA_APP_HOME")
        if env_home:
            app_home = Path(env_home)

    # Merge TOML dicts: defaults first, user second, profile third
    merged: dict[str, Any] = {}

    defaults_toml = _load_toml(_DEFAULTS_DIR / "settings.toml")
    _deep_merge(merged, defaults_toml)

    if app_home is not None:
        user_toml = _load_toml(app_home / "config" / "settings.toml")
        _deep_merge(merged, user_toml)

        if profile:
            profile_toml = _load_toml(app_home / "config" / "profiles" / profile / "settings.toml")
            _deep_merge(merged, profile_toml)

        # workspace.toml — written atomically by /setworkfolder; loaded last so
        # it takes precedence over settings.toml for [workspace] keys only.
        workspace_toml = _load_toml(app_home / "config" / "workspace.toml")
        _deep_merge(merged, workspace_toml)

    try:
        # Use Settings(**merged) instead of model_validate so that
        # pydantic-settings also reads environment variables (env > TOML > defaults).
        return Settings(**merged)
    except Exception as exc:
        raise InvalidConfigError(f"Settings validation failed: {exc}", original=exc) from exc


def save_workspace_settings(workfolder_path: str, app_home: Path) -> None:
    """
    Persist the workspace folder path to ``<app_home>/config/workspace.toml``.

    Writing to a dedicated file keeps it atomic and prevents any risk of
    corrupting the main ``settings.toml``.
    """
    path = app_home / "config" / "workspace.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"[workspace]\nworkfolder_path = {workfolder_path!r}\n",
        encoding="utf-8",
    )


def load_registry_toml(name: str, app_home: Path | None = None) -> dict[str, Any]:
    """
    Load one of the registry TOML files.

    Args:
        name:     File name without extension (e.g. "model_registry").
        app_home: App home directory. Falls back to bundled defaults.
    """
    result: dict[str, Any] = {}

    default_path = _DEFAULTS_DIR / f"{name}.toml"
    _deep_merge(result, _load_toml(default_path))

    if app_home is not None:
        user_path = app_home / "config" / f"{name}.toml"
        _deep_merge(result, _load_toml(user_path))

    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge ``override`` into ``base`` in-place."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
