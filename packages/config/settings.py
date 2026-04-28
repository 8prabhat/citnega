"""
Pydantic-settings Settings class for Citnega.

Precedence (highest to lowest):
  1. CLI flags (injected by bootstrap before instantiation)
  2. Environment variables  CITNEGA_*
  3. User config file       <app_home>/config/settings.toml
  4. Bundled defaults       packages/config/defaults/settings.toml
"""

from __future__ import annotations

from pydantic import Field, SecretStr
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
    # Per-event timeout — must be large enough to cover slow tool calls (network,
    # LLM inference, file I/O).  60 s was too short for long-running agents.
    stream_timeout_seconds: float = 3600.0
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
    # How many times to retry a streaming request on connection/timeout errors.
    streaming_max_retries: int = 2
    # Circuit breaker: open after this many consecutive failures.
    circuit_breaker_threshold: int = 5
    # Circuit breaker: seconds before transitioning OPEN → HALF_OPEN.
    circuit_breaker_cooldown_seconds: float = 30.0

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
    recent_turns_count: int = 10
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
    strict_workspace_loading: bool = False

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
    # When True, ALL approval checks and policy gates are bypassed.
    # DANGEROUS — intended only for local dev/debug. Shown in red in the TUI when on.
    bypass_permissions: bool = False

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

    Nextgen is the default active path; set env vars CITNEGA_NEXTGEN__*=false to revert.
    """

    planning_enabled: bool = True
    execution_enabled: bool = True
    workflows_enabled: bool = True
    skills_enabled: bool = True
    parallel_execution_enabled: bool = True

    model_config = SettingsConfigDict(env_prefix="CITNEGA_NEXTGEN_")


class OpenRouterSettings(BaseSettings):
    """OpenRouter provider configuration — uses LiteLLMProvider internally."""

    enabled: bool = Field(default=False, description="Enable OpenRouter as a provider option.")
    api_key: SecretStr = Field(default=SecretStr(""), description="OpenRouter API key.")
    default_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Default model ID (e.g. 'anthropic/claude-opus-4', 'openai/gpt-4o').",
    )
    site_url: str = Field(default="", description="Optional app URL for OpenRouter rankings.")
    app_name: str = Field(default="citnega", description="App name sent to OpenRouter.")

    model_config = SettingsConfigDict(env_prefix="CITNEGA_OPENROUTER_")


class MCPServerConfig(BaseSettings):
    """Configuration for a single MCP server connection."""

    name: str = Field(description="Unique name for this MCP server.")
    transport: str = Field(default="stdio", description="Transport: stdio | sse | streamable_http.")
    command: list[str] = Field(default_factory=list, description="Command + args for stdio transport.")
    url: str = Field(default="", description="Server URL for sse/streamable_http transport.")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables for the server process.")
    enabled: bool = Field(default=True)
    timeout_seconds: float = Field(default=30.0)
    requires_approval: bool = Field(default=False, description="Whether tool calls to this server need user approval.")
    description: str = Field(default="")
    tags: list[str] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_prefix="")  # no prefix — used as nested model


class MCPSettings(BaseSettings):
    """Global MCP configuration."""

    enabled: bool = Field(default=False, description="Enable MCP server connections.")
    servers: list[MCPServerConfig] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_prefix="CITNEGA_MCP_")


class DockerSettings(BaseSettings):
    """Docker execution backend settings."""

    enabled: bool = Field(default=False, description="Use Docker for shell command execution.")
    image: str = Field(default="python:3.12-slim", description="Docker image to use.")
    workdir: str = Field(default="/workspace", description="Working directory inside the container.")
    memory_limit: str = Field(default="512m", description="Memory limit (e.g. '512m', '2g').")
    cpu_limit: float = Field(default=1.0, description="CPU limit (number of cores).")
    network_disabled: bool = Field(default=True, description="Disable network access in container.")
    read_only: bool = Field(default=True, description="Mount container filesystem as read-only.")
    pids_limit: int = Field(default=64, description="Maximum number of processes in container.")

    model_config = SettingsConfigDict(env_prefix="CITNEGA_DOCKER_")


class TelegramSettings(BaseSettings):
    """Telegram bot messaging settings."""

    enabled: bool = Field(default=False)
    bot_token: SecretStr = Field(default=SecretStr(""), description="Telegram bot token.")
    default_chat_id: str = Field(default="", description="Default chat ID to send messages to.")

    model_config = SettingsConfigDict(env_prefix="CITNEGA_TELEGRAM_")


class DiscordSettings(BaseSettings):
    """Discord bot messaging settings."""

    enabled: bool = Field(default=False)
    bot_token: SecretStr = Field(default=SecretStr(""), description="Discord bot token.")
    default_channel_id: str = Field(default="", description="Default channel ID to send messages to.")

    model_config = SettingsConfigDict(env_prefix="CITNEGA_DISCORD_")


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
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    docker: DockerSettings = Field(default_factory=DockerSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)

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
