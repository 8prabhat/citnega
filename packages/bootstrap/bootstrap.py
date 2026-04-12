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
import sys
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import configure_logging, runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.runtime.app_service import ApplicationService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session

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


class _PassThroughContextHandler(IContextHandler):
    """Identity handler ensuring ContextAssembler has at least one handler."""

    @property
    def name(self) -> str:
        return "pass_through"

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        return context


def _select_adapter(framework: str, path_resolver):  # type: ignore[no-untyped-def]
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
        elif framework == "stub":
            # Allowed in test / dev contexts; not for production use
            from tests.fixtures.stub_adapter import StubFrameworkAdapter

            return StubFrameworkAdapter()
        else:
            runtime_logger.error(
                "bootstrap_unknown_framework",
                framework=framework,
                supported=["adk", "langgraph", "crewai"],
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


async def _build_model_gateway(settings, emitter):  # type: ignore[no-untyped-def]
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
            gateway.register_provider(model_info.model_id, provider)
        except Exception as exc:
            runtime_logger.warning(
                "bootstrap_provider_init_failed",
                model_id=model_info.model_id,
                error=str(exc),
            )

    # Health-check providers
    healthy_count = 0
    for _model_id, provider in gateway.providers.items():
        try:
            healthy = await provider.health_check()
            if healthy:
                healthy_count += 1
        except Exception:
            pass  # health_check failures are non-fatal individually

    local_only: bool = getattr(settings.runtime, "local_only", True)
    if healthy_count == 0 and local_only:
        runtime_logger.error(
            "bootstrap_no_healthy_provider",
            local_only=local_only,
            registered=len(list(gateway.providers.keys())),
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
            from citnega.packages.config.loaders import load_settings
            from citnega.packages.storage.path_resolver import PathResolver
            from citnega.packages.workspace.overlay import resolve_workfolder_path

            path_resolver = PathResolver(app_home=app_home or (db_path.parent if db_path else None))
            settings = load_settings(app_home=path_resolver.app_home)
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

            CompositeKeyStore([KeyringKeyStore(), EnvVarKeyStore()])
        except Exception as exc:
            runtime_logger.warning("bootstrap_keystore_init_failed", error=str(exc))
            from citnega.packages.security.key_store import EnvVarKeyStore

            EnvVarKeyStore()  # type: ignore[assignment]

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

        # ── Step 7: Repositories & managers ──────────────────────────────────
        from citnega.packages.runtime.runs import RunManager
        from citnega.packages.runtime.sessions import SessionManager
        from citnega.packages.storage.repositories.run_repo import RunRepository
        from citnega.packages.storage.repositories.session_repo import SessionRepository

        session_repo = SessionRepository(db)
        run_repo = RunRepository(db)
        session_mgr = SessionManager(session_repo)
        run_mgr = RunManager(run_repo)

        # ── Step 8: Event emitter ─────────────────────────────────────────────
        from citnega.packages.runtime.events.emitter import EventEmitter

        emitter = EventEmitter(event_log_dir=path_resolver.event_logs_dir)

        # ── Step 9: Policy ────────────────────────────────────────────────────
        from citnega.packages.runtime.policy.approval_manager import ApprovalManager
        from citnega.packages.runtime.policy.enforcer import PolicyEnforcer

        approval_mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, approval_mgr)

        # ── Step 10: Framework adapter ────────────────────────────────────────
        _framework = framework or settings.runtime.framework
        adapter = _select_adapter(_framework, path_resolver)
        from citnega.packages.protocol.interfaces.adapter import AdapterConfig

        await adapter.initialize(
            AdapterConfig(
                framework_name=adapter.framework_name,
                default_model_id=settings.runtime.default_model_id,
            )
        )

        # ── Step 11: Model gateway ────────────────────────────────────────────
        if not skip_provider_health_check:
            try:
                await _build_model_gateway(settings, emitter)
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

        assembler = ContextAssembler(
            [
                _PassThroughContextHandler(),
                KBRetrievalHandler(kb_store=kb_store),
            ]
        )

        # ── Step 14: Tracer ───────────────────────────────────────────────────
        from citnega.packages.runtime.events.tracer import Tracer
        from citnega.packages.storage.repositories.invocation_repo import InvocationRepository

        tracer = Tracer(InvocationRepository(db))

        # ── Step 15: Tool registry ────────────────────────────────────────────
        from citnega.packages.tools.registry import ToolRegistry
        from citnega.packages.workspace.overlay import load_workspace_overlay

        tool_registry = ToolRegistry(
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            path_resolver=path_resolver,
            kb_store=kb_store,
        )
        built_in_tools = tool_registry.build_all()
        workspace_overlay = load_workspace_overlay(
            workfolder_root,
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            tool_registry=built_in_tools,
        )
        tools = {**built_in_tools, **workspace_overlay.tools}

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
        AgentRegistry.wire_core_agents(agents, tools)

        # ── Step 17: Unified callable registry ───────────────────────────────
        from citnega.packages.shared.registry import BaseRegistry

        registry: BaseRegistry = BaseRegistry()
        for name, callable_obj in {**tools, **agents}.items():
            try:
                registry.register(name, callable_obj)
            except Exception:
                pass

        runtime_logger.info(
            "bootstrap_callables_loaded",
            tools=len(tools),
            agents=len(agents),
            total=len(tools) + len(agents),
        )

        # ── Step 18: CoreRuntime ──────────────────────────────────────────────
        from citnega.packages.runtime.core_runtime import CoreRuntime

        runtime = CoreRuntime(
            session_manager=session_mgr,
            run_manager=run_mgr,
            context_assembler=assembler,
            framework_adapter=adapter,
            event_emitter=emitter,
            callable_registry=registry,
        )

        # ── Step 19: ApplicationService ───────────────────────────────────────
        svc = ApplicationService(
            runtime=runtime,
            emitter=emitter,
            approval_manager=approval_mgr,
            kb_store=kb_store,
            tool_registry=tools,
            agent_registry=agents,
            enforcer=enforcer,
            tracer=tracer,
            app_home=path_resolver.app_home,
        )

        runtime_logger.info(
            "bootstrap_complete",
            framework=_framework,
            db=str(resolved_db),
        )
        yield svc
    finally:
        if runtime is not None:
            await runtime.shutdown()
        if db is not None:
            await db.disconnect()
        runtime_logger.info("bootstrap_shutdown_complete")
