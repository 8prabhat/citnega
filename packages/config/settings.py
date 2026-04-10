"""
Pydantic-settings Settings class for Citnega.

Precedence (highest to lowest):
  1. CLI flags (injected by bootstrap before instantiation)
  2. Environment variables  CITNEGA_*
  3. User config file       <app_home>/config/settings.toml
  4. Bundled defaults       packages/config/defaults/settings.toml
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    framework:           str  = "adk"
    default_model_id:    str  = "gemma3-12b-local"
    local_only:          bool = True
    max_callable_depth:  int  = 2

    model_config = SettingsConfigDict(env_prefix="CITNEGA_RUNTIME_")


class SessionSettings(BaseSettings):
    max_context_tokens:       int = 8192
    approval_timeout_seconds: int = 300

    model_config = SettingsConfigDict(env_prefix="CITNEGA_SESSION_")


class LoggingSettings(BaseSettings):
    level:          str = "INFO"
    retention_days: int = 30
    format:         str = "jsonl"

    model_config = SettingsConfigDict(env_prefix="CITNEGA_LOGGING_")


class TUISettings(BaseSettings):
    theme:        str  = "default"
    mouse_enabled: bool = False
    history_size: int  = 1000

    model_config = SettingsConfigDict(env_prefix="CITNEGA_TUI_")


class ContextSettings(BaseSettings):
    handlers: list[str] = Field(default_factory=lambda: [
        "recent_turns",
        "session_summary",
        "kb_retrieval",
        "runtime_state",
        "token_budget",
    ])
    recent_turns_count:  int = 20
    kb_retrieval_limit:  int = 5

    model_config = SettingsConfigDict(env_prefix="CITNEGA_CONTEXT_")


class SecuritySettings(BaseSettings):
    log_file_permissions:    str = "0600"
    config_file_permissions: str = "0600"
    data_dir_permissions:    str = "0700"

    model_config = SettingsConfigDict(env_prefix="CITNEGA_SECURITY_")


class ConversationSettings(BaseSettings):
    """
    Controls session management and conversation compaction behaviour.

    Compaction replaces old messages with a model-generated (or count-based)
    summary so the context window stays within budget.

    Fields
    ------
    auto_compact
        Enable automatic compaction when a threshold is hit.
    compact_threshold_messages
        Trigger compaction when the conversation has this many messages.
        Set to 0 to disable message-count based trigger.
    compact_threshold_tokens
        Trigger compaction when estimated token usage exceeds this value.
        Set to 0 to disable token-count based trigger.
    compact_keep_recent
        After compaction, keep this many of the most recent messages verbatim.
    compact_use_model
        If true, ask the model to write the summary; otherwise use a plain
        message-count fallback (works without a live model server).
    max_sessions_shown
        How many sessions to display in the session-picker screen.
    auto_name_from_first_message
        Automatically rename a new session from the first user message.
    """

    auto_compact:                  bool = True
    compact_threshold_messages:    int  = 50
    compact_threshold_tokens:      int  = 6000
    compact_keep_recent:           int  = 10
    compact_use_model:             bool = True
    max_sessions_shown:            int  = 20
    auto_name_from_first_message:  bool = True

    model_config = SettingsConfigDict(env_prefix="CITNEGA_CONVERSATION_")


class Settings(BaseSettings):
    """Root settings object — single entry point for all configuration."""

    runtime:      RuntimeSettings      = Field(default_factory=RuntimeSettings)
    session:      SessionSettings      = Field(default_factory=SessionSettings)
    logging:      LoggingSettings      = Field(default_factory=LoggingSettings)
    tui:          TUISettings          = Field(default_factory=TUISettings)
    context:      ContextSettings      = Field(default_factory=ContextSettings)
    security:     SecuritySettings     = Field(default_factory=SecuritySettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)

    model_config = SettingsConfigDict(
        env_prefix="CITNEGA_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls: type, **kwargs: object) -> tuple[object, ...]:  # type: ignore[override]
        # env vars take priority over TOML init values (which are passed as kwargs)
        env = kwargs.get("env_settings")
        init = kwargs.get("init_settings")
        dotenv = kwargs.get("dotenv_settings")
        secrets = kwargs.get("secrets_settings") or kwargs.get("file_secret_settings")
        return tuple(s for s in (env, init, dotenv, secrets) if s is not None)
