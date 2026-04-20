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
from urllib.parse import urlparse

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
    _out_raw: dict | None = None,
) -> Settings:
    """
    Load and merge all settings into a single validated Settings object.

    Args:
        app_home: Override the app home directory (useful in tests).
        profile:  Profile name (e.g. "dev"). Loaded from
                  <app_home>/config/profiles/<profile>/settings.toml.
    """
    # Resolve app_home: explicit arg → env var → PathResolver default
    if app_home is None:
        env_home = os.environ.get("CITNEGA_APP_HOME")
        if env_home:
            app_home = Path(env_home)
        else:
            try:
                from citnega.packages.storage.path_resolver import PathResolver
                app_home = PathResolver().app_home
            except Exception:
                pass

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

    # Expose the merged raw TOML to callers that need it (e.g. validate_settings).
    if _out_raw is not None:
        _out_raw.update(merged)

    try:
        # Use Settings(**merged) instead of model_validate so that
        # pydantic-settings also reads environment variables (env > TOML > defaults).
        return Settings(**merged)
    except Exception as exc:
        raise InvalidConfigError(f"Settings validation failed: {exc}", original=exc) from exc


_KNOWN_FRAMEWORKS = {"adk", "langgraph", "crewai", "direct", "stub"}
_KNOWN_HANDLERS = {"recent_turns", "session_summary", "kb_retrieval", "runtime_state", "token_budget"}
_KNOWN_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_KNOWN_POLICY_TEMPLATES = {"dev", "team", "locked_down"}
_KNOWN_REMOTE_WORKER_MODES = {"inprocess", "http"}
_KNOWN_REMOTE_ISOLATION_PROFILES = {"process", "container"}
_KNOWN_REMOTE_CONTAINER_RUNTIMES = {"docker", "podman"}
_KNOWN_TOML_SECTIONS = {
    "runtime", "session", "logging", "tui", "context",
    "security", "conversation", "workspace", "policy", "remote", "nextgen",
}


def validate_settings(settings: Settings, raw_toml: dict | None = None) -> list[str]:
    """
    Run semantic validation on *settings* and return a list of error strings.

    An empty list means everything is valid.  Callers should treat a non-empty
    list as a configuration error and fail fast before the runtime starts.

    Args:
        settings:  Fully loaded Settings object.
        raw_toml:  The merged raw TOML dict (before pydantic parsing) so we
                   can detect unknown top-level section names.
    """
    errors: list[str] = []

    # 1. Framework
    framework = settings.runtime.framework.lower().strip()
    if framework not in _KNOWN_FRAMEWORKS:
        errors.append(
            f"[runtime] framework = {settings.runtime.framework!r} is not valid. "
            f"Supported values: {sorted(_KNOWN_FRAMEWORKS - {'stub'})}."
        )

    # 2. Context handlers
    for handler in settings.context.handlers:
        if handler not in _KNOWN_HANDLERS:
            errors.append(
                f"[context] handlers contains unknown handler {handler!r}. "
                f"Known handlers: {sorted(_KNOWN_HANDLERS)}."
            )

    # 3. Log level
    if settings.logging.level.upper() not in _KNOWN_LOG_LEVELS:
        errors.append(
            f"[logging] level = {settings.logging.level!r} is not valid. "
            f"Supported: {sorted(_KNOWN_LOG_LEVELS)}."
        )

    # 3b. Policy template
    policy_template = settings.policy.template.strip().lower().replace("-", "_")
    if policy_template not in _KNOWN_POLICY_TEMPLATES:
        errors.append(
            f"[policy] template = {settings.policy.template!r} is not valid. "
            f"Supported: {sorted(_KNOWN_POLICY_TEMPLATES)}."
        )

    # 3c. Workspace onboarding constraints
    manifest_path = settings.workspace.onboarding_manifest_path.strip()
    if not manifest_path:
        errors.append("[workspace] onboarding_manifest_path must be a non-empty string.")

    if (
        settings.workspace.onboarding_require_signature
        and not settings.workspace.onboarding_require_manifest
    ):
        errors.append(
            "[workspace] onboarding_require_signature=true requires "
            "onboarding_require_manifest=true."
        )

    if (
        settings.workspace.onboarding_require_signature
        and not settings.workspace.onboarding_signature_key.strip()
    ):
        errors.append(
            "[workspace] onboarding_require_signature=true requires a non-empty "
            "onboarding_signature_key (or CITNEGA_WORKSPACE_ONBOARDING_SIGNATURE_KEY)."
        )

    for publisher in settings.workspace.onboarding_trusted_publishers:
        if not str(publisher).strip():
            errors.append(
                "[workspace] onboarding_trusted_publishers cannot include empty values."
            )
            break

    # 3d. Remote execution constraints
    remote_mode = settings.remote.worker_mode.strip().lower()
    if remote_mode not in _KNOWN_REMOTE_WORKER_MODES:
        errors.append(
            f"[remote] worker_mode = {settings.remote.worker_mode!r} is not valid. "
            f"Supported: {sorted(_KNOWN_REMOTE_WORKER_MODES)}."
        )

    if settings.remote.workers < 1:
        errors.append("[remote] workers must be >= 1.")

    if settings.remote.simulate_latency_ms < 0:
        errors.append("[remote] simulate_latency_ms must be >= 0.")

    if settings.remote.request_timeout_ms < 1:
        errors.append("[remote] request_timeout_ms must be >= 1.")

    if not settings.remote.service_host.strip():
        errors.append("[remote] service_host must be a non-empty string.")

    if not (1 <= settings.remote.service_port <= 65535):
        errors.append("[remote] service_port must be between 1 and 65535.")

    isolation_profile = settings.remote.service_isolation_profile.strip().lower()
    if isolation_profile not in _KNOWN_REMOTE_ISOLATION_PROFILES:
        errors.append(
            f"[remote] service_isolation_profile = {settings.remote.service_isolation_profile!r} "
            f"is not valid. Supported: {sorted(_KNOWN_REMOTE_ISOLATION_PROFILES)}."
        )

    if (
        settings.remote.enabled
        and settings.remote.require_signed_envelopes
        and not settings.remote.envelope_signing_key.strip()
    ):
        errors.append(
            "[remote] enabled=true with require_signed_envelopes=true requires "
            "remote.envelope_signing_key (or CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY)."
        )

    if settings.remote.envelope_signing_key.strip() and not settings.remote.envelope_signing_key_id.strip():
        errors.append(
            "[remote] envelope_signing_key_id must be a non-empty string when "
            "remote.envelope_signing_key is configured."
        )

    if bool(settings.remote.client_cert_path.strip()) != bool(settings.remote.client_key_path.strip()):
        errors.append(
            "[remote] client_cert_path and client_key_path must be configured together for mTLS."
        )

    try:
        verification_key_map = _parse_remote_verification_keys(
            settings.remote.envelope_verification_keys
        )
    except ValueError as exc:
        errors.append(f"[remote] {exc}")
    else:
        active_key_id = settings.remote.envelope_signing_key_id.strip()
        active_key = settings.remote.envelope_signing_key.strip()
        if active_key and active_key_id:
            existing = verification_key_map.get(active_key_id)
            if existing and existing != active_key:
                errors.append(
                    f"[remote] envelope_verification_keys entry for {active_key_id!r} "
                    "must match remote.envelope_signing_key when both are provided."
                )

    for callable_name in settings.remote.allowed_callables:
        if not str(callable_name).strip():
            errors.append("[remote] allowed_callables cannot include empty values.")
            break

    service_tls_cert = settings.remote.service_tls_cert_path.strip()
    service_tls_key = settings.remote.service_tls_key_path.strip()
    service_tls_client_ca = settings.remote.service_tls_client_ca_path.strip()
    if bool(service_tls_cert) != bool(service_tls_key):
        errors.append(
            "[remote] service_tls_cert_path and service_tls_key_path must be configured together."
        )
    if settings.remote.service_tls_require_client_cert and not service_tls_client_ca:
        errors.append(
            "[remote] service_tls_require_client_cert=true requires "
            "remote.service_tls_client_ca_path."
        )
    if service_tls_client_ca and not service_tls_cert:
        errors.append(
            "[remote] service_tls_client_ca_path requires HTTPS worker service "
            "(set service_tls_cert_path and service_tls_key_path)."
        )

    if isolation_profile == "container":
        container_runtime = settings.remote.service_container_runtime.strip().lower()
        if container_runtime not in _KNOWN_REMOTE_CONTAINER_RUNTIMES:
            errors.append(
                "[remote] service_container_runtime must be one of "
                f"{sorted(_KNOWN_REMOTE_CONTAINER_RUNTIMES)} when "
                "service_isolation_profile='container'."
            )
        if not settings.remote.service_container_image.strip():
            errors.append(
                "[remote] service_isolation_profile='container' requires non-empty "
                "remote.service_container_image."
            )

    if remote_mode == "http":
        endpoint = settings.remote.http_endpoint.strip()
        if not endpoint:
            errors.append(
                "[remote] worker_mode='http' requires non-empty remote.http_endpoint "
                "(or CITNEGA_REMOTE_HTTP_ENDPOINT)."
            )
        else:
            parsed = urlparse(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(
                    f"[remote] http_endpoint = {settings.remote.http_endpoint!r} is not valid. "
                    "Expected absolute http(s) URL."
                )

    # 4. Unknown top-level TOML sections (catch typos like [runtiem])
    if raw_toml:
        unknown = set(raw_toml.keys()) - _KNOWN_TOML_SECTIONS
        for key in sorted(unknown):
            errors.append(
                f"Unknown config section [{key}] — check for typos. "
                f"Known sections: {sorted(_KNOWN_TOML_SECTIONS)}."
            )

    return errors


def save_general_settings(section: str, values: dict, app_home: Path) -> None:
    """
    Persist a section of settings to ``<app_home>/config/settings.toml``.

    Merges ``values`` into the existing user settings.toml under ``[section]``
    (e.g. section="runtime", section="conversation") without touching other
    sections.  Written atomically via a temp file.
    """
    import tomllib

    settings_path = app_home / "config" / "settings.toml"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if settings_path.exists():
        try:
            with settings_path.open("rb") as fh:
                existing = tomllib.load(fh)
        except Exception:
            existing = {}

    section_data = dict(existing.get(section, {}))
    section_data.update(values)
    existing[section] = section_data

    # Serialise to TOML manually (no tomli_w dependency required)
    lines: list[str] = []
    for sec, data in existing.items():
        lines.append(f"[{sec}]")
        for k, v in data.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, str):
                lines.append(f"{k} = {v!r}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif isinstance(v, list):
                items = ", ".join(repr(x) for x in v)
                lines.append(f"{k} = [{items}]")
        lines.append("")

    tmp = settings_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    import os as _os
    _os.replace(tmp, settings_path)


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


def _parse_remote_verification_keys(entries: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in entries:
        entry = str(raw_entry).strip()
        key_id, sep, secret = entry.partition("=")
        if not sep:
            raise ValueError(
                "envelope_verification_keys entries must use the format 'key_id=secret'."
            )
        key_id = key_id.strip()
        secret = secret.strip()
        if not key_id or not secret:
            raise ValueError(
                "envelope_verification_keys entries require non-empty key ids and secrets."
            )
        existing = parsed.get(key_id)
        if existing and existing != secret:
            raise ValueError(
                f"envelope_verification_keys contains duplicate key id {key_id!r} "
                "with different values."
            )
        parsed[key_id] = secret
    return parsed
