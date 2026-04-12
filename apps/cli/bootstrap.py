"""
CLI bootstrap — composition root for the headless CLI and TUI.

Wires:
  - SQLite storage (sessions, runs, invocations)
  - EventEmitter + Tracer (observability)
  - PolicyEnforcer (security / approval)
  - ToolRegistry → all built-in tools pre-instantiated
  - AgentRegistry → all agents pre-instantiated with tools injected
  - KnowledgeStore (KB)
  - DirectModelAdapter (LLM provider)
  - ApplicationService facade

Usage::

    async with cli_bootstrap() as svc:
        await svc.create_session(...)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.runtime.app_service import ApplicationService
from citnega.packages.runtime.context.assembler import ContextAssembler
from citnega.packages.runtime.core_runtime import CoreRuntime
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.runtime.runs import RunManager
from citnega.packages.runtime.sessions import SessionManager
from citnega.packages.shared.registry import BaseRegistry
from citnega.packages.storage.database import DatabaseFactory
from citnega.packages.storage.path_resolver import PathResolver
from citnega.packages.storage.repositories.invocation_repo import InvocationRepository
from citnega.packages.storage.repositories.run_repo import RunRepository
from citnega.packages.storage.repositories.session_repo import SessionRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session

# ── Minimal pass-through context handler ──────────────────────────────────────


class _PassThroughContextHandler(IContextHandler):
    """Identity handler — returns the ContextObject unchanged."""

    @property
    def name(self) -> str:
        return "pass_through"

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        return context


# ── Bootstrap ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def cli_bootstrap(
    *,
    db_path: Path | None = None,
    app_home: Path | None = None,
    run_migrations: bool = True,
) -> AsyncIterator[ApplicationService]:
    """
    Async context manager that creates and tears down an ApplicationService.

    All infrastructure is created here following DIP — application code
    never imports concrete infrastructure classes directly.
    """
    db = None
    runtime = None

    try:
        # ── Paths ──────────────────────────────────────────────────────────────
        from citnega.packages.config.loaders import load_settings
        from citnega.packages.workspace.overlay import (
            load_workspace_overlay,
            resolve_workfolder_path,
        )

        path_resolver = PathResolver(app_home=app_home or (db_path.parent if db_path else None))
        settings = load_settings(app_home=path_resolver.app_home)
        workfolder_root = resolve_workfolder_path(settings.workspace.workfolder_path)
        path_resolver = PathResolver(
            app_home=path_resolver.app_home,
            workfolder_root=workfolder_root,
        )
        resolved_db = db_path or path_resolver.db_path
        path_resolver.create_all()

        # ── Database ───────────────────────────────────────────────────────────
        db = DatabaseFactory(resolved_db)
        if run_migrations:
            alembic_ini = path_resolver.alembic_ini_path()
            if alembic_ini.exists():
                try:
                    await db.run_migrations(alembic_ini)
                except Exception as exc:
                    runtime_logger.warning("cli_migration_skipped", reason=str(exc))
        await db.connect()

        # ── Repositories ───────────────────────────────────────────────────────
        session_repo = SessionRepository(db)
        run_repo = RunRepository(db)
        invocation_repo = InvocationRepository(db)
        session_mgr = SessionManager(session_repo)
        run_mgr = RunManager(run_repo)

        # ── Observability ──────────────────────────────────────────────────────
        emitter = EventEmitter(event_log_dir=path_resolver.event_logs_dir)

        from citnega.packages.runtime.events.tracer import Tracer

        tracer = Tracer(invocation_repo)

        # ── Policy ─────────────────────────────────────────────────────────────
        approval_mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, approval_mgr)

        # ── Knowledge base ─────────────────────────────────────────────────────
        from citnega.packages.kb.store import KnowledgeStore

        kb_store = KnowledgeStore(db, path_resolver)

        # ── Tools ──────────────────────────────────────────────────────────────
        from citnega.packages.tools.registry import ToolRegistry

        tool_registry = ToolRegistry(
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            path_resolver=path_resolver,
            kb_store=kb_store,
        )
        built_in_tools: dict = tool_registry.build_all()
        workspace_overlay = load_workspace_overlay(
            workfolder_root,
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            tool_registry=built_in_tools,
        )
        tools: dict = {**built_in_tools, **workspace_overlay.tools}

        # ── Agents ─────────────────────────────────────────────────────────────
        from citnega.packages.agents.registry import AgentRegistry

        agent_registry = AgentRegistry(
            enforcer=enforcer,
            emitter=emitter,
            tracer=tracer,
            tools=tools,
        )
        built_in_agents: dict = agent_registry.build_all()
        agents: dict = {
            **built_in_agents,
            **workspace_overlay.agents,
            **workspace_overlay.workflows,
        }
        AgentRegistry.wire_core_agents(agents, tools)

        # ── Unified registry ───────────────────────────────────────────────────
        registry: BaseRegistry = BaseRegistry()
        for callable_obj in {**tools, **agents}.values():
            try:
                registry.register(callable_obj.name, callable_obj)
            except Exception:
                pass

        # ── Framework adapter ──────────────────────────────────────────────────
        from citnega.packages.adapters.direct.adapter import DirectModelAdapter
        from citnega.packages.protocol.interfaces.adapter import AdapterConfig

        adapter = DirectModelAdapter(sessions_dir=path_resolver.sessions_dir)
        await adapter.initialize(
            AdapterConfig(
                framework_name=adapter.framework_name,
                default_model_id=settings.runtime.default_model_id,
            )
        )

        # ── Context assembler ──────────────────────────────────────────────────
        from citnega.packages.runtime.context.handlers.kb_retrieval import (
            KBRetrievalHandler,
        )

        assembler = ContextAssembler(
            [
                _PassThroughContextHandler(),
                KBRetrievalHandler(kb_store=kb_store),
            ]
        )

        # ── CoreRuntime ────────────────────────────────────────────────────────
        runtime = CoreRuntime(
            session_manager=session_mgr,
            run_manager=run_mgr,
            context_assembler=assembler,
            framework_adapter=adapter,
            event_emitter=emitter,
            callable_registry=registry,
        )

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
        yield svc
    finally:
        if runtime is not None:
            await runtime.shutdown()
        if db is not None:
            await db.disconnect()
        runtime_logger.info("cli_bootstrap_shutdown")
