"""
packages/bootstrap/bootstrap.py — Full 28-step composition root.

Startup sequence (fail-fast with stable exit codes):
  2 — configuration invalid or missing required fields
  3 — framework adapter initialisation failed
  4 — no healthy model provider and local_only=True
  5 — database migration failed

Usage::

    async with create_application() as svc:
        run_id = await svc.run_turn(session_id, "hello")

For the CLI / TUI, call the top-level ``bootstrap()`` coroutine which
handles SystemExit on every failure mode.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import configure_logging, runtime_logger
from citnega.packages.runtime.app_service import ApplicationService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from citnega.packages.config.settings import CitnegaSettings
    from citnega.packages.model_gateway.gateway import ModelGateway
    from citnega.packages.protocol.interfaces.adapter import IFrameworkAdapter
    from citnega.packages.protocol.interfaces.events import IEventEmitter
    from citnega.packages.storage.path_resolver import PathResolver

# ---------------------------------------------------------------------------
# Exit code constants
# ---------------------------------------------------------------------------

EXIT_CONFIG_ERROR = 2
EXIT_ADAPTER_ERROR = 3
EXIT_NO_PROVIDER = 4
EXIT_MIGRATION_ERROR = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------



def _select_adapter(framework: str, path_resolver: PathResolver) -> IFrameworkAdapter:
    """
    Return the correct IFrameworkAdapter instance for the configured framework.

    Raises SystemExit(EXIT_ADAPTER_ERROR) on unknown framework or import failure.
    """
    framework = framework.lower().strip()
    try:
        if framework == "adk":
            from citnega.packages.adapters.adk.adapter import ADKFrameworkAdapter

            return ADKFrameworkAdapter(path_resolver)
        elif framework == "langgraph":
            from citnega.packages.adapters.langgraph.adapter import LangGraphFrameworkAdapter

            return LangGraphFrameworkAdapter(path_resolver)
        elif framework == "crewai":
            from citnega.packages.adapters.crewai.adapter import CrewAIFrameworkAdapter

            return CrewAIFrameworkAdapter(path_resolver)
        elif framework == "direct":
            from citnega.packages.adapters.direct.adapter import DirectModelAdapter

            return DirectModelAdapter(path_resolver.sessions_dir)
        elif framework == "stub":
            # Allowed in test / dev contexts; not for production use
            from tests.fixtures.stub_adapter import StubFrameworkAdapter

            return StubFrameworkAdapter()
        else:
            runtime_logger.error(
                "bootstrap_unknown_framework",
                framework=framework,
                supported=["adk", "langgraph", "crewai", "direct"],
            )
            sys.exit(EXIT_ADAPTER_ERROR)
    except ImportError as exc:
        runtime_logger.error(
            "bootstrap_adapter_import_failed",
            framework=framework,
            error=str(exc),
        )
        sys.exit(EXIT_ADAPTER_ERROR)
    except Exception as exc:
        runtime_logger.error(
            "bootstrap_adapter_init_failed",
            framework=framework,
            error=str(exc),
        )
        sys.exit(EXIT_ADAPTER_ERROR)


async def _build_model_gateway(settings: CitnegaSettings, emitter: IEventEmitter) -> ModelGateway:
    """
    Build and health-check the ModelGateway.

    Steps:
    - Load model registry (model_registry.toml).
    - Instantiate providers for each registered model.
    - Apply rate-limit configuration.
    - Health-check all providers; if local_only=True and none are healthy, exit(4).
    """
    from citnega.packages.model_gateway.gateway import ModelGateway
    from citnega.packages.model_gateway.providers.custom_remote import CustomRemoteProvider
    from citnega.packages.model_gateway.providers.ollama import OllamaProvider
    from citnega.packages.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
    from citnega.packages.model_gateway.providers.vllm import VLLMProvider
    from citnega.packages.model_gateway.rate_limiter import TokenBucketRateLimiter
    from citnega.packages.model_gateway.registry import ModelRegistry

    model_registry = ModelRegistry()
    try:
        model_registry.load()
    except Exception as exc:
        runtime_logger.warning("bootstrap_model_registry_load_failed", error=str(exc))
        # Non-fatal — gateway will have no models registered; provider health
        # check below will decide whether to exit.

    rate_limiter = TokenBucketRateLimiter()
    gateway = ModelGateway(
        registry=model_registry,
        rate_limiter=rate_limiter,
        event_emitter=emitter,
    )

    # Register providers for each known model
    _PROVIDER_MAP = {
        "ollama": OllamaProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "vllm": VLLMProvider,
        "custom_remote": CustomRemoteProvider,
    }

    for model_info in model_registry.list_all():
        provider_cls = _PROVIDER_MAP.get(model_info.provider_type)
        if provider_cls is None:
            runtime_logger.warning(
                "bootstrap_unknown_provider_type",
                model_id=model_info.model_id,
                provider_type=model_info.provider_type,
            )
            continue
        try:
            provider = provider_cls(model_info)
            gateway.register_provider(provider)
        except Exception as exc:
            runtime_logger.warning(
                "bootstrap_provider_init_failed",
                model_id=model_info.model_id,
                error=str(exc),
            )

    # Health-check providers
    healthy_count = 0
    for _model_id, provider in gateway.list_providers().items():
        try:
            healthy = await provider.health_check()
            if healthy:
                healthy_count += 1
        except Exception as exc:
            runtime_logger.warning(
                "provider_health_check_failed",
                model_id=_model_id,
                error=str(exc),
            )

    local_only: bool = getattr(settings.runtime, "local_only", True)
    if healthy_count == 0 and local_only:
        runtime_logger.error(
            "bootstrap_no_healthy_provider",
            local_only=local_only,
            registered=len(gateway.list_providers()),
        )
        sys.exit(EXIT_NO_PROVIDER)

    return gateway


# ---------------------------------------------------------------------------
# Public context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def create_application(
    *,
    db_path: Path | None = None,
    app_home: Path | None = None,
    framework: str | None = None,
    run_migrations: bool = True,
    skip_provider_health_check: bool = False,
) -> AsyncIterator[ApplicationService]:
    """
    Full 28-step composition root.

    Args:
        db_path:                    Override DB path (tests / alternate profile).
        app_home:                   Override app home (tests / isolated profiles).
        framework:                  Override framework from settings (test injection).
        run_migrations:             Run Alembic migrations on startup.
        skip_provider_health_check: Skip the provider health check (used in tests).

    Yields:
        A fully initialised ApplicationService.

    Exit codes on failure:
        2 — configuration error
        3 — adapter init failed
        4 — no healthy provider (local_only mode)
        5 — migration failed
    """
    db = None
    runtime = None

    try:
        # ── Step 1: Load and validate settings ────────────────────────────────
        try:
            from citnega.packages.config.loaders import load_settings, validate_settings
            from citnega.packages.storage.path_resolver import PathResolver
            from citnega.packages.workspace.overlay import resolve_workfolder_path

            path_resolver = PathResolver(app_home=app_home or (db_path.parent if db_path else None))
            _raw_toml: dict = {}
            settings = load_settings(app_home=path_resolver.app_home, _out_raw=_raw_toml)

            _config_errors = validate_settings(settings, raw_toml=_raw_toml)
            if _config_errors:
                for _err in _config_errors:
                    print(f"[citnega] Config error: {_err}", file=sys.stderr)
                sys.exit(EXIT_CONFIG_ERROR)

            workfolder_root = resolve_workfolder_path(settings.workspace.workfolder_path)
            path_resolver = PathResolver(
                app_home=path_resolver.app_home,
                workfolder_root=workfolder_root,
            )
        except Exception as exc:
            print(f"[citnega] Configuration error: {exc}", file=sys.stderr)
            sys.exit(EXIT_CONFIG_ERROR)

        # ── Step 2: Configure structured logging ──────────────────────────────
        try:
            configure_logging(level=settings.logging.level)
        except Exception as exc:
            print(f"[citnega] Logging configuration failed: {exc}", file=sys.stderr)

        runtime_logger.info("bootstrap_start")

        # ── Step 3: Create app directories ────────────────────────────────────
        try:
            path_resolver.create_all()
        except Exception as exc:
            runtime_logger.warning("bootstrap_dir_creation_failed", error=str(exc))

        # ── Step 4: Key store ─────────────────────────────────────────────────
        try:
            from citnega.packages.security.key_store import (
                CompositeKeyStore,
                EnvVarKeyStore,
                KeyringKeyStore,
            )

            key_store = CompositeKeyStore([KeyringKeyStore(), EnvVarKeyStore()])
        except Exception as exc:
            runtime_logger.warning("bootstrap_keystore_init_failed", error=str(exc))
            from citnega.packages.security.key_store import EnvVarKeyStore

            key_store = EnvVarKeyStore()
        runtime_logger.debug("bootstrap_keystore_ready", implementation=type(key_store).__name__)

        # ── Step 5: Database (connect + WAL PRAGMAs) ──────────────────────────
        from citnega.packages.storage.database import DatabaseFactory

        resolved_db = db_path or path_resolver.db_path
        db = DatabaseFactory(resolved_db)

        # ── Step 6: Alembic migrations ────────────────────────────────────────
        if run_migrations:
            alembic_ini = path_resolver.alembic_ini_path()
            if alembic_ini.exists():
                try:
                    await db.run_migrations(alembic_ini)
                except Exception as exc:
                    runtime_logger.error(
                        "bootstrap_migration_failed",
                        error=str(exc),
                        alembic_ini=str(alembic_ini),
                    )
                    sys.exit(EXIT_MIGRATION_ERROR)
            else:
                runtime_logger.warning(
                    "bootstrap_alembic_ini_missing",
                    path=str(alembic_ini),
                )

        await db.connect()

        # Resolve active framework once so all downstream components agree.
        _framework = framework or settings.runtime.framework

        # ── Step 7: Repositories & managers ──────────────────────────────────
        from citnega.packages.runtime.runs import RunManager
        from citnega.packages.runtime.sessions import SessionManager
        from citnega.packages.storage.repositories.run_repo import RunRepository
        from citnega.packages.storage.repositories.session_repo import SessionRepository

        session_repo = SessionRepository(db)
        run_repo = RunRepository(db)
        session_mgr = SessionManager(
            session_repo,
            default_framework=_framework,
            strict_framework_validation=settings.runtime.strict_framework_validation,
            active_frameworks=frozenset({_framework}),
        )
        run_mgr = RunManager(run_repo)

        # ── Step 8: Event emitter ─────────────────────────────────────────────
        from citnega.packages.runtime.events.emitter import EventEmitter

        emitter = EventEmitter(
            event_log_dir=path_resolver.event_logs_dir,
            max_queue_size=settings.runtime.event_queue_max_size,
        )

        # ── Step 9: Policy ────────────────────────────────────────────────────
        from citnega.packages.runtime.policy.approval_manager import ApprovalManager
        from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
        from citnega.packages.runtime.policy.templates import (
            apply_policy_template_to_tools,
            resolve_policy_template,
        )

        approval_mgr = ApprovalManager()
        effective_policy = resolve_policy_template(settings.policy)
        # Build path variable map for policy substitution in allowed_paths.
        # Tools can declare allowed_paths=["${WORKSPACE_ROOT}"] to allow the
        # configured workspace directory without hardcoding absolute paths.
        _workspace_root = (
            settings.policy.workspace_root
            or settings.workspace.workfolder_path
            or str(path_resolver.app_home)
        )
        _policy_path_vars = {
            "WORKSPACE_ROOT": _workspace_root,
            "APP_HOME": str(path_resolver.app_home),
        }
        enforcer = PolicyEnforcer(
            emitter,
            approval_mgr,
            deny_network=effective_policy.enforce_network_deny,
            path_vars=_policy_path_vars,
            bypass_permissions=settings.policy.bypass_permissions,
        )

        # ── Step 10: Framework adapter ────────────────────────────────────────
        adapter = _select_adapter(_framework, path_resolver)
        from citnega.packages.protocol.interfaces.adapter import AdapterConfig

        await adapter.initialize(
            AdapterConfig(
                framework_name=adapter.framework_name,
                default_model_id=settings.runtime.default_model_id,
            )
        )

        # ── Step 11: Model gateway ────────────────────────────────────────────
        model_gateway = None
        if not skip_provider_health_check:
            try:
                model_gateway = await _build_model_gateway(settings, emitter)
            except SystemExit:
                raise
            except Exception as exc:
                runtime_logger.error("bootstrap_model_gateway_failed", error=str(exc))
                sys.exit(EXIT_ADAPTER_ERROR)

        # ── Step 12: Knowledge base ───────────────────────────────────────────
        from citnega.packages.kb.store import KnowledgeStore

        kb_store = KnowledgeStore(db, path_resolver)

        # ── Step 13: Context handlers ─────────────────────────────────────────
        from citnega.packages.runtime.context.assembler import ContextAssembler
        from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler
        from citnega.packages.runtime.context.handlers.recent_turns import RecentTurnsHandler
        from citnega.packages.runtime.context.handlers.runtime_state import RuntimeStateHandler
        from citnega.packages.runtime.context.handlers.session_summary import SessionSummaryHandler
        from citnega.packages.runtime.context.handlers.token_budget import TokenBudgetHandler
        from citnega.packages.storage.repositories.message_repo import MessageRepository

        _KNOWN_HANDLERS = frozenset(
            {"recent_turns", "session_summary", "kb_retrieval", "runtime_state", "token_budget"}
        )
        _unknown = [h for h in settings.context.handlers if h not in _KNOWN_HANDLERS]
        if _unknown:
            if settings.context.strict_handler_loading:
                from citnega.packages.shared.errors import InvalidConfigError as _ICE

                raise _ICE(
                    f"Unknown context handler(s) in config: {_unknown}. "
                    "Set strict_handler_loading=false to skip unknown handlers."
                )
            else:
                runtime_logger.warning("unknown_context_handlers_skipped", handlers=_unknown)

        message_repo = MessageRepository(db)
        handler_names = [h for h in settings.context.handlers if h in _KNOWN_HANDLERS]
        if not handler_names:
            from citnega.packages.shared.errors import InvalidConfigError as _ICE

            raise _ICE(
                "No valid context handlers configured. "
                "At least one of recent_turns/session_summary/kb_retrieval/"
                "runtime_state/token_budget is required."
            )

        if "token_budget" in handler_names and handler_names[-1] != "token_budget":
            runtime_logger.warning(
                "token_budget_handler_reordered",
                original_order=handler_names,
            )
            handler_names = [h for h in handler_names if h != "token_budget"] + ["token_budget"]

        _handler_factories = {
            "recent_turns": lambda: RecentTurnsHandler(
                message_repo,
                recent_turns_count=settings.context.recent_turns_count,
            ),
            "session_summary": lambda: SessionSummaryHandler(run_repo),
            "kb_retrieval": lambda: KBRetrievalHandler(kb_store=kb_store),
            "runtime_state": lambda: RuntimeStateHandler(),
            "token_budget": lambda: TokenBudgetHandler(
                max_context_tokens=settings.session.max_context_tokens,
                emitter=emitter,
                priorities=dict(settings.context.token_budget_priorities),
                default_priority=settings.context.token_budget_default_priority,
            ),
        }

        assembler = ContextAssembler(
            [_handler_factories[name]() for name in handler_names],
            handler_timeout_ms=settings.context.handler_timeout_ms,
        )

        # ── Step 14: Tracer ───────────────────────────────────────────────────
        from citnega.packages.runtime.events.tracer import Tracer
        from citnega.packages.storage.repositories.invocation_repo import InvocationRepository

        tracer = Tracer(InvocationRepository(db))

        # ── Step 14b: Execution backend (local or Docker) ─────────────────────
        try:
            from citnega.packages.execution.backends.factory import ExecutionBackendFactory
            execution_backend = ExecutionBackendFactory.create(settings)
        except Exception as exc:
            runtime_logger.warning("bootstrap_execution_backend_failed", error=str(exc))
            execution_backend = None

        # ── Step 15: Tool registry ────────────────────────────────────────────
        from citnega.packages.tools.registry import ToolRegistry
        from citnega.packages.workspace.overlay import load_workspace_overlay

        tool_registry = ToolRegistry(
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            path_resolver=path_resolver,
            kb_store=kb_store,
            execution_backend=execution_backend,
        )
        built_in_tools = tool_registry.build_all()
        workspace_overlay = load_workspace_overlay(
            workfolder_root,
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            tool_registry=built_in_tools,
            workspace_settings=settings.workspace,
            nextgen_workflows_enabled=settings.nextgen.workflows_enabled,
        )
        tools = {**built_in_tools, **workspace_overlay.tools}
        apply_policy_template_to_tools(
            tools,
            effective_policy,
            workspace_root=_workspace_root,
            app_home=path_resolver.app_home,
        )
        runtime_logger.info(
            "policy_template_applied",
            template=effective_policy.template_name,
            enforce_network_deny=effective_policy.enforce_network_deny,
            enforce_workspace_bounds=effective_policy.enforce_workspace_bounds,
            approval_tools=len(effective_policy.require_approval_tools),
        )

        # ── Step 16: Agent registry ───────────────────────────────────────────
        from citnega.packages.agents.registry import AgentRegistry

        agent_registry = AgentRegistry(
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            tools=tools,
        )
        built_in_agents = agent_registry.build_all()
        agents = {
            **built_in_agents,
            **workspace_overlay.agents,
            **workspace_overlay.workflows,
        }
        from citnega.packages.agents.core.orchestrator_agent import OrchestratorAgent

        for _agent in agents.values():
            if isinstance(_agent, OrchestratorAgent):
                try:
                    _agent.configure_remote_execution(settings.remote)
                except Exception as exc:
                    runtime_logger.warning(
                        "agent_remote_configuration_failed",
                        agent=getattr(_agent, "name", "<unknown>"),
                        error=str(exc),
                    )
        AgentRegistry.wire_core_agents(agents, tools)

        # ── Step 17: Unified callable registry ───────────────────────────────
        from citnega.packages.shared.registry import CallableRegistry

        registry = CallableRegistry()
        for name, callable_obj in {**tools, **agents}.items():
            try:
                registry.register(name, callable_obj)
            except Exception as exc:
                runtime_logger.error(
                    "callable_registration_failed",
                    name=name,
                    error=str(exc),
                )

        runtime_logger.info(
            "bootstrap_callables_loaded",
            tools=len(tools),
            agents=len(agents),
            total=len(tools) + len(agents),
        )

        # ── Step 17a: MCP Manager (optional — connects configured MCP servers) ─
        mcp_manager = None
        try:
            mcp_settings = getattr(settings, "mcp", None)
            if mcp_settings is not None and getattr(mcp_settings, "enabled", False):
                from citnega.packages.mcp.manager import MCPManager
                mcp_manager = MCPManager(
                    settings=mcp_settings,
                    enforcer=enforcer,
                    emitter=emitter,
                    tracer=tracer,
                )
                await mcp_manager.start()
                for bridge_tool in mcp_manager.get_bridge_tools().values():
                    tools[bridge_tool.name] = bridge_tool
                    try:
                        registry.register(bridge_tool.name, bridge_tool)
                    except Exception as _reg_exc:
                        runtime_logger.warning("bootstrap_mcp_bridge_register_failed", name=bridge_tool.name, error=str(_reg_exc))
                runtime_logger.info(
                    "bootstrap_mcp_ready",
                    bridge_tools=len(mcp_manager.get_bridge_tools()),
                )
        except Exception as exc:
            runtime_logger.warning("bootstrap_mcp_failed", error=str(exc))
            mcp_manager = None

        # ── Step 17b: CapabilityRegistry + ExecutionEngine ───────────────────
        from citnega.packages.capabilities.providers import (
            BuiltinCapabilityProvider,
            BuiltinSkillProvider,
            MentalModelCapabilityProvider,
            WorkspaceCapabilityProvider,
        )
        from citnega.packages.capabilities.registry import CapabilityRegistry as _CapReg
        from citnega.packages.execution.engine import ExecutionEngine

        cap_registry = _CapReg()
        _cap_records, _cap_diagnostics = BuiltinCapabilityProvider().load({**tools, **agents})
        cap_registry.register_many(_cap_records, overwrite=True)
        _skill_records, _ = BuiltinSkillProvider().load()
        cap_registry.register_many(_skill_records, overwrite=False)  # workspace skills take priority
        if _cap_diagnostics.has_required_failures:
            runtime_logger.warning(
                "bootstrap_capability_registry_failures",
                failures=len(_cap_diagnostics.failures),
            )

        # Load workspace capabilities (skills, workflows, mental models)
        try:
            from citnega.packages.config.loaders import load_settings as _ls
            _wf_path = _ls().workspace.workfolder_path
            _ws_root = Path(_wf_path).expanduser() if _wf_path else None
        except Exception:
            _ws_root = None

        if _ws_root is not None:
            _ws_records, _ = WorkspaceCapabilityProvider(_ws_root).load()
            cap_registry.register_many(_ws_records, overwrite=True)
            _mm_records, _ = MentalModelCapabilityProvider(_ws_root).load()
            cap_registry.register_many(_mm_records, overwrite=True)

        runtime_logger.info(
            "bootstrap_capability_registry_loaded",
            capabilities=len(cap_registry),
        )
        execution_engine = ExecutionEngine(event_emitter=emitter)
        adapter.set_capability_registry(cap_registry)

        # ── Step 18: CoreRuntime ──────────────────────────────────────────────
        from citnega.packages.runtime.core_runtime import CoreRuntime

        runtime = CoreRuntime(
            session_manager=session_mgr,
            run_manager=run_mgr,
            context_assembler=assembler,
            framework_adapter=adapter,
            event_emitter=emitter,
            callable_registry=registry,
            model_gateway=model_gateway,
            capability_registry=cap_registry,
            execution_engine=execution_engine,
        )

        # ── Step 19: ApplicationService ───────────────────────────────────────
        svc = ApplicationService(
            runtime=runtime,
            emitter=emitter,
            approval_manager=approval_mgr,
            kb_store=kb_store,
            callable_registry=registry,
            enforcer=enforcer,
            tracer=tracer,
            app_home=path_resolver.app_home,
        )

        # ── Step 19a: Skill improver (wired into direct runner when available) ─
        try:
            if model_gateway is not None and _framework == "direct":
                from citnega.packages.skills.improver import SkillImprover
                _skill_improver = SkillImprover(model_gateway=model_gateway, settings=settings)
                # Inject into all runners managed by the adapter
                _adapter_inner = getattr(adapter, "_adapter", adapter)
                _runners = getattr(_adapter_inner, "_runners", {})
                for _runner in _runners.values():
                    if hasattr(_runner, "_skill_improver"):
                        _runner._skill_improver = _skill_improver
                # Also patch new runner creation via adapter hook (best-effort)
                _orig_create = getattr(_adapter_inner, "_create_runner", None)
                if _orig_create is not None:
                    def _patched_create(*args, **kwargs):
                        r = _orig_create(*args, **kwargs)
                        if hasattr(r, "_skill_improver"):
                            r._skill_improver = _skill_improver
                        return r
                    _adapter_inner._create_runner = _patched_create
        except Exception as exc:
            runtime_logger.warning("bootstrap_skill_improver_failed", error=str(exc))

        # ── Step 19b: Messaging gateway + heartbeat engine ────────────────────
        _messaging_gateway = None
        _heartbeat_engine = None
        try:
            from citnega.packages.messaging.gateway import MessagingGateway
            channels = []
            _tg_settings = getattr(settings, "telegram", None)
            if _tg_settings is not None and getattr(_tg_settings, "enabled", False):
                from citnega.packages.messaging.channels.telegram import TelegramChannel
                channels.append(TelegramChannel(_tg_settings))
            _dc_settings = getattr(settings, "discord", None)
            if _dc_settings is not None and getattr(_dc_settings, "enabled", False):
                from citnega.packages.messaging.channels.discord import DiscordChannel
                channels.append(DiscordChannel(_dc_settings))
            if channels:
                _messaging_gateway = MessagingGateway(channels)
                from citnega.packages.messaging.heartbeat import HeartbeatEngine
                _heartbeat_engine = HeartbeatEngine(
                    workfolder=workfolder_root,
                    gateway=_messaging_gateway,
                    app_service=svc,
                )
                _heartbeat_engine.start()
                runtime_logger.info(
                    "bootstrap_messaging_ready",
                    channels=[c.channel_name for c in channels],
                )
        except Exception as exc:
            runtime_logger.warning("bootstrap_messaging_failed", error=str(exc))

        runtime_logger.info(
            "bootstrap_complete",
            framework=_framework,
            db=str(resolved_db),
        )

        # Emit startup diagnostics event so event consumers can confirm
        # bootstrap succeeded and surface any skipped checks.
        from citnega.packages.protocol.events.diagnostics import StartupDiagnosticsEvent

        _diag_checks = ["db_connection", "adapter_init", "callable_registry"]
        _diag_failures: list[str] = []
        if skip_provider_health_check:
            _diag_checks.append("model_gateway")
            _diag_failures.append("model_gateway")  # skipped = treated as degraded
        _diag_status = "degraded" if _diag_failures else "passed"
        emitter.emit(
            StartupDiagnosticsEvent(
                session_id="",
                run_id="",
                checks=_diag_checks,
                status=_diag_status,
                failures=_diag_failures,
                details={"model_gateway": "skipped in test mode"} if skip_provider_health_check else {},
            )
        )

        yield svc
    finally:
        try:
            if "_heartbeat_engine" in dir() and _heartbeat_engine is not None:
                await _heartbeat_engine.stop()
        except Exception as _he_exc:
            runtime_logger.warning("bootstrap_heartbeat_stop_failed", error=str(_he_exc))
        try:
            if "mcp_manager" in dir() and mcp_manager is not None:
                await mcp_manager.stop()
        except Exception as _mcp_exc:
            runtime_logger.warning("bootstrap_mcp_stop_failed", error=str(_mcp_exc))
        if runtime is not None:
            await runtime.shutdown()
        if db is not None:
            await db.disconnect()
        runtime_logger.info("bootstrap_shutdown_complete")
