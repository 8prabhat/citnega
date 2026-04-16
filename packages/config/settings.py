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
    framework: str = "adk"
    default_model_id: str = "gemma4-26b-local"
    local_only: bool = True
    max_callable_depth: int = 2
    # When True, reject session creation if the requested framework is not
    # registered with the current adapter.  When False (default), unknown
    # frameworks fall back to the configured default silently.
    strict_framework_validation: bool = False
    # Seconds to wait for the next streaming event before disconnecting.
    stream_timeout_seconds: float = 60.0
    # Maximum number of per-run event queue slots before events are dropped.
    event_queue_max_size: int = 256
    # Maximum tool-call rounds per LLM turn (prevents infinite tool loops).
    max_tool_rounds: int = 5
    # Maximum supervisor rounds in ConversationAgent before bailing out.
    max_supervisor_rounds: int = 3
    # Seconds to drain event queues during graceful shutdown.
    shutdown_drain_timeout_seconds: float = 5.0
    # How many times to retry a failed provider request with exponential backoff.
    provider_max_retries: int = 3

    model_config = SettingsConfigDict(env_prefix="CITNEGA_RUNTIME_")


class SessionSettings(BaseSettings):
    max_context_tokens: int = 8192
    approval_timeout_seconds: int = 300

    model_config = SettingsConfigDict(env_prefix="CITNEGA_SESSION_")


class LoggingSettings(BaseSettings):
    level: str = "INFO"
    retention_days: int = 30
    format: str = "jsonl"

    model_config = SettingsConfigDict(env_prefix="CITNEGA_LOGGING_")


class TUISettings(BaseSettings):
    theme: str = "default"
    mouse_enabled: bool = False
    history_size: int = 1000
    # Maximum entries to store in the chat input history.
    input_history_size: int = 200

    model_config = SettingsConfigDict(env_prefix="CITNEGA_TUI_")


class ContextSettings(BaseSettings):
    handlers: list[str] = Field(
        default_factory=lambda: [
            "recent_turns",
            "session_summary",
            "kb_retrieval",
            "runtime_state",
            "token_budget",
        ]
    )
    recent_turns_count: int = 20
    kb_retrieval_limit: int = 5
    # When True, a handler name in the config that cannot be resolved to a
    # known handler class raises a startup error.  When False (default),
    # unknown handler names are skipped with a warning.
    strict_handler_loading: bool = False
    # Per-handler timeout in milliseconds.  0 = no timeout (default).
    handler_timeout_ms: int = 0
    # Maximum tokens per KB document chunk during ingestion.
    kb_chunk_size_tokens: int = 512
    # Priority scores for token-budget handler; sources not listed get default_priority.
    token_budget_priorities: dict[str, int] = Field(
        default_factory=lambda: {
            "recent_turns": 100,
            "state": 80,
            "summary": 60,
            "kb": 40,
        }
    )
    # Priority assigned to any source_type not in token_budget_priorities.
    token_budget_default_priority: int = 20

    model_config = SettingsConfigDict(env_prefix="CITNEGA_CONTEXT_")


class SecuritySettings(BaseSettings):
    log_file_permissions: str = "0600"
    config_file_permissions: str = "0600"
    data_dir_permissions: str = "0700"

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

    auto_compact: bool = True
    compact_threshold_messages: int = 50
    compact_threshold_tokens: int = 6000
    compact_keep_recent: int = 10
    compact_use_model: bool = True
    max_sessions_shown: int = 20
    auto_name_from_first_message: bool = True

    model_config = SettingsConfigDict(env_prefix="CITNEGA_CONVERSATION_")


class WorkspaceSettings(BaseSettings):
    """
    Controls the user workspace where custom agents, tools, and workflows live.

    Fields
    ------
    workfolder_path
        Absolute path to the workspace folder.  Empty string means "use the
        directory where citnega was launched" (CWD at startup).
    auto_refresh
        If true, automatically reload the workspace on every startup.
    onboarding_manifest_path
        Relative (or absolute) path to the bundle manifest used for workspace
        onboarding verification.
    onboarding_require_manifest
        When true, startup/hot-reload fails if the manifest is missing.
    onboarding_require_signature
        When true, the bundle manifest must include a valid signature.
    onboarding_signature_key
        Shared secret used for HMAC verification of bundle manifests.
    onboarding_trusted_publishers
        Optional allowlist of accepted publishers in bundle provenance.
    onboarding_enforce_file_coverage
        When true, every loadable workspace module must be declared in the
        bundle manifest file list.
    """

    workfolder_path: str = ""
    auto_refresh: bool = False
    onboarding_manifest_path: str = ".citnega/bundle_manifest.json"
    onboarding_require_manifest: bool = False
    onboarding_require_signature: bool = False
    onboarding_signature_key: str = ""
    onboarding_trusted_publishers: list[str] = Field(default_factory=list)
    onboarding_enforce_file_coverage: bool = True

    model_config = SettingsConfigDict(env_prefix="CITNEGA_WORKSPACE_")


class PolicySettings(BaseSettings):
    """Runtime policy enforcement knobs."""

    # Environment policy template:
    # dev | team | locked_down
    template: str = "dev"
    # When True, any callable with network_allowed=True is blocked at invoke time.
    # Useful for air-gapped / restricted environments.
    enforce_network_deny: bool = False
    # Additional tools that must require approval (beyond template defaults).
    require_approval_tools: list[str] = Field(default_factory=list)
    # When True, file tools are constrained to workspace/app-home paths.
    enforce_workspace_bounds: bool = False
    # Workspace root resolved at runtime.  Empty = use WorkspaceSettings.workfolder_path.
    workspace_root: str = ""

    model_config = SettingsConfigDict(env_prefix="CITNEGA_POLICY_")


class RemoteExecutionSettings(BaseSettings):
    """
    Controls remote worker execution and signed run envelopes.

    Fields
    ------
    enabled
        Enables remote dispatch capabilities for orchestrators.
    worker_mode
        Remote backend mode. Supported: ``inprocess`` or ``http``.
    workers
        Number of worker slots available for remote dispatch.
    require_signed_envelopes
        When true, remote dispatch requires a valid signed run envelope.
    envelope_signing_key
        Shared HMAC key used to sign and verify run envelopes.
    envelope_signing_key_id
        Key identifier embedded into newly signed envelopes.
    envelope_verification_keys
        Additional accepted verification keys using ``key_id=secret`` entries.
    simulate_latency_ms
        Optional deterministic latency injection for remote calls.
    allowed_callables
        Optional allowlist; empty means all callables may run remotely.
    http_endpoint
        Remote HTTP endpoint used when ``worker_mode=http``.
    request_timeout_ms
        End-to-end HTTP request timeout in milliseconds.
    auth_token
        Optional bearer token for HTTP remote dispatch requests.
    verify_tls
        When false, HTTPS certificate verification is disabled.
    ca_cert_path
        Optional CA bundle used by remote HTTP clients to verify worker certificates.
    client_cert_path
        Optional client certificate used for mTLS remote worker auth.
    client_key_path
        Optional private key paired with ``client_cert_path``.
    service_host
        Bind host used by the reference remote worker service process.
    service_port
        Bind port used by the reference remote worker service process.
    service_isolation_profile
        Service isolation declaration. Supported: ``process`` or ``container``.
    service_container_runtime
        Container runtime used to launch the reference worker when the isolation
        profile is ``container``.
    service_container_image
        Container image used by the built-in container launcher.
    service_container_name
        Optional explicit container name; empty means Citnega derives one.
    service_tls_cert_path
        TLS server certificate presented by the reference remote worker service.
    service_tls_key_path
        TLS private key paired with ``service_tls_cert_path``.
    service_tls_client_ca_path
        Optional CA bundle used to validate incoming client certificates.
    service_tls_require_client_cert
        When true, the reference remote worker service enforces mTLS.
    """

    enabled: bool = False
    worker_mode: str = "inprocess"
    workers: int = 2
    require_signed_envelopes: bool = True
    envelope_signing_key: str = ""
    envelope_signing_key_id: str = "current"
    envelope_verification_keys: list[str] = Field(default_factory=list)
    simulate_latency_ms: int = 0
    allowed_callables: list[str] = Field(default_factory=list)
    http_endpoint: str = ""
    request_timeout_ms: int = 15000
    auth_token: str = ""
    verify_tls: bool = True
    ca_cert_path: str = ""
    client_cert_path: str = ""
    client_key_path: str = ""
    service_host: str = "127.0.0.1"
    service_port: int = 8787
    service_isolation_profile: str = "process"
    service_container_runtime: str = "docker"
    service_container_image: str = ""
    service_container_name: str = ""
    service_tls_cert_path: str = ""
    service_tls_key_path: str = ""
    service_tls_client_ca_path: str = ""
    service_tls_require_client_cert: bool = False

    model_config = SettingsConfigDict(env_prefix="CITNEGA_REMOTE_")


class NextgenSettings(BaseSettings):
    """
    Feature gates for the Nextgen planning/execution stack.

    All gates default to false so the legacy runtime remains the active path
    until parity and rollout criteria are met.
    """

    planning_enabled: bool = False
    execution_enabled: bool = False
    workflows_enabled: bool = False
    skills_enabled: bool = False
    parallel_execution_enabled: bool = False

    model_config = SettingsConfigDict(env_prefix="CITNEGA_NEXTGEN_")


class Settings(BaseSettings):
    """Root settings object — single entry point for all configuration."""

    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    tui: TUISettings = Field(default_factory=TUISettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    remote: RemoteExecutionSettings = Field(default_factory=RemoteExecutionSettings)
    nextgen: NextgenSettings = Field(default_factory=NextgenSettings)

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
