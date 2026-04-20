"""
ApplicationService — IApplicationService facade over CoreRuntime.

This is the single object that CLI and TUI depend on.  Nothing here imports
framework adapters, storage drivers, or infrastructure directly — all of that
is injected at construction time by the bootstrap (Phase 9) or the lightweight
CLI bootstrap (Phase 6).
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.events.lifecycle import RunCompleteEvent
from citnega.packages.protocol.interfaces.application_service import IApplicationService
from citnega.packages.protocol.models.approvals import ApprovalStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from citnega.packages.capabilities import CapabilityDescriptor, CapabilityRegistry
    from citnega.packages.planning import CompiledPlan
    from citnega.packages.protocol.callables.types import CallableMetadata
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.interfaces.adapter import IFrameworkRunner
    from citnega.packages.protocol.interfaces.events import ITracer
    from citnega.packages.protocol.interfaces.knowledge_store import IKnowledgeStore
    from citnega.packages.protocol.interfaces.model_gateway import IModelGateway
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer
    from citnega.packages.protocol.models import (
        KBItem,
        KBSearchResult,
        ModelInfo,
        RunSummary,
        Session,
        SessionConfig,
        StateSnapshot,
    )
    from citnega.packages.runtime.core_runtime import CoreRuntime
    from citnega.packages.runtime.events.emitter import EventEmitter
    from citnega.packages.runtime.policy.approval_manager import ApprovalManager
    from citnega.packages.shared.registry import CallableRegistry


class ApplicationService(IApplicationService):
    """
    Concrete IApplicationService.

    All access to runtime internals goes through CoreRuntime's public API
    or the typed IFrameworkRunner interface.  No private-attribute access.
    """

    def __init__(
        self,
        runtime: CoreRuntime,
        emitter: EventEmitter,
        approval_manager: ApprovalManager,
        *,
        model_gateway: IModelGateway | None = None,
        kb_store: IKnowledgeStore | None = None,
        callable_registry: CallableRegistry | None = None,
        enforcer: IPolicyEnforcer | None = None,
        tracer: ITracer | None = None,
        app_home: Path | None = None,
    ) -> None:
        self._runtime = runtime
        self._emitter = emitter
        self._approval_manager = approval_manager
        self._model_gateway = model_gateway
        self._kb_store = kb_store
        self._callable_registry: CallableRegistry
        if callable_registry is not None:
            self._callable_registry = callable_registry
        else:
            from citnega.packages.shared.registry import CallableRegistry as _CR
            self._callable_registry = _CR()
        self._enforcer = enforcer
        self._tracer = tracer
        self._app_home = app_home
        self._capability_registry_cache: CapabilityRegistry | None = None

    # ── Session management ─────────────────────────────────────────────────────

    async def create_session(self, config: SessionConfig) -> Session:
        return await self._runtime.create_session(config)

    async def get_session(self, session_id: str) -> Session | None:
        try:
            return await self._runtime.get_session(session_id)
        except Exception:
            return None

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        return await self._runtime.list_sessions(limit=limit)

    async def delete_session(self, session_id: str) -> None:
        await self._runtime.delete_session(session_id)

    async def update_session_strategy(self, session_id: str, strategy: Any) -> None:
        """Apply a StrategySpec to the active session and persist it."""
        await self._runtime.update_session_strategy(session_id, strategy)

    # ── Run execution ──────────────────────────────────────────────────────────

    async def run_turn(self, session_id: str, user_input: str) -> str:
        run_id = await self._runtime.run_turn(session_id, user_input)

        # Load settings once per turn — shared by compact + rename checks below.
        try:
            from citnega.packages.config.loaders import load_settings as _ls
            _turn_settings = _ls()
        except Exception:
            _turn_settings = None

        # Auto-compact if thresholds are exceeded
        try:
            await self._maybe_auto_compact(session_id, _turn_settings)
        except Exception as exc:
            from citnega.packages.observability.logging_setup import runtime_logger as _log
            _log.warning("auto_compact_failed", session_id=session_id, error=str(exc))

        # Auto-rename new session from first user message
        try:
            await self._maybe_auto_rename(session_id, user_input, _turn_settings)
        except Exception as exc:
            from citnega.packages.observability.logging_setup import runtime_logger as _log
            _log.debug("auto_rename_failed", session_id=session_id, error=str(exc))

        return run_id

    async def _maybe_auto_compact(self, session_id: str, settings: Any = None) -> None:
        """Trigger compaction when configured thresholds are exceeded."""
        if settings is None:
            from citnega.packages.config.loaders import load_settings
            settings = load_settings()
        cfg = settings.conversation

        if not cfg.auto_compact:
            return

        stats = self.get_conversation_stats(session_id)
        msg_over = (
            cfg.compact_threshold_messages > 0
            and stats["message_count"] >= cfg.compact_threshold_messages
        )
        token_over = (
            cfg.compact_threshold_tokens > 0
            and stats["token_estimate"] >= cfg.compact_threshold_tokens
        )

        if msg_over or token_over:
            from citnega.packages.observability.logging_setup import runtime_logger

            runtime_logger.info(
                "auto_compact_triggered",
                session_id=session_id,
                message_count=stats["message_count"],
                token_estimate=stats["token_estimate"],
            )
            await self.compact_conversation(session_id)

    async def _maybe_auto_rename(self, session_id: str, user_input: str, settings: Any = None) -> None:
        """Rename a brand-new session to the first user message text."""
        if settings is None:
            from citnega.packages.config.loaders import load_settings
            settings = load_settings()
        if not settings.conversation.auto_name_from_first_message:
            return

        try:
            session = await self._runtime.get_session(session_id)
        except Exception:
            return

        # Only rename if it still has the default placeholder name
        if session.config.name not in ("new-session", "tui-session", "bootstrap-test", "turn-test"):
            return

        # Derive a short name from the first message
        name = user_input.strip().splitlines()[0][:60] or "session"
        await self.rename_session(session_id, name)

    async def stream_events(self, run_id: str) -> AsyncIterator[CanonicalEvent]:
        """
        Async generator: yields events for *run_id* until RunCompleteEvent
        arrives or the stream times out.

        The per-event timeout (stream_timeout_seconds, default 3600) prevents
        hanging forever when a run crashes without emitting RunCompleteEvent.
        It must be large enough to cover the slowest tool calls.
        """
        from citnega.packages.config.loaders import load_settings

        try:
            timeout = load_settings().runtime.stream_timeout_seconds
        except Exception:
            timeout = 3600.0

        queue = self._emitter.get_queue(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout)
                except TimeoutError:
                    # No event arrived within the window — run likely crashed.
                    # Log and exit; _drain() will post RunFinished to unblock the UI.
                    from citnega.packages.observability.logging_setup import runtime_logger as _log
                    _log.warning("stream_events_timeout", run_id=run_id, timeout=timeout)
                    break
                yield event
                if isinstance(event, RunCompleteEvent):
                    break
        finally:
            self._emitter.close_queue(run_id)

    async def get_run(self, run_id: str) -> RunSummary | None:
        return await self._runtime.get_run_summary(run_id)

    async def list_runs(self, session_id: str, limit: int = 50) -> list[RunSummary]:
        return await self._runtime.list_runs_for_session(session_id, limit=limit)

    # ── Run control ────────────────────────────────────────────────────────────

    async def pause_run(self, run_id: str) -> None:
        await self._runtime.pause_run(run_id)

    async def resume_run(self, run_id: str) -> None:
        await self._runtime.resume_run(run_id)

    async def cancel_run(self, run_id: str) -> None:
        await self._runtime.cancel_run(run_id)

    async def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        note: str | None = None,
    ) -> None:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        await self._approval_manager.resolve(approval_id, status, user_note=note)

    # ── Introspection ──────────────────────────────────────────────────────────

    async def get_state_snapshot(self, session_id: str) -> StateSnapshot:
        return await self._runtime.get_state_snapshot(session_id)

    # ── Knowledge base ─────────────────────────────────────────────────────────

    async def search_kb(self, query: str, limit: int = 10) -> list[KBSearchResult]:
        if self._kb_store is None:
            return []
        return await self._kb_store.search(query, limit=limit)

    async def add_kb_item(self, item: KBItem) -> KBItem:
        if self._kb_store is None:
            raise NotImplementedError("Knowledge base is not available (kb_store not injected).")
        return await self._kb_store.add_item(item)

    async def delete_kb_item(self, item_id: str) -> None:
        if self._kb_store is None:
            raise NotImplementedError("Knowledge base is not available (kb_store not injected).")
        await self._kb_store.delete_item(item_id)

    # ── Import / export ────────────────────────────────────────────────────────

    async def export_session(
        self,
        session_id: str,
        fmt: str = "jsonl",
        output_path: Path | None = None,
    ) -> Path:
        """Export KB items to JSONL or Markdown."""
        if self._kb_store is None:
            raise NotImplementedError("Session export requires a KB store.")
        scoped_id = None if session_id in ("all", None) else session_id
        return await self._kb_store.export_all(fmt=fmt, output_path=output_path, session_id=scoped_id)

    async def import_session(self, path: Path) -> Session:
        """
        Import a conversation from a JSONL or JSON file and create a new session.

        Each line in JSONL must be a JSON object with 'role' and 'content' keys.
        JSON files must have a top-level 'messages' list with the same structure.
        Returns the newly created Session.
        """
        import json as _json

        from citnega.packages.protocol.models.sessions import SessionConfig

        raw = path.read_text(encoding="utf-8").strip()
        messages: list[dict[str, str]] = []

        if path.suffix.lower() in (".jsonl",) or (raw and not raw.startswith(("{", "["))):
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "role" in obj and "content" in obj:
                    messages.append({"role": str(obj["role"]), "content": str(obj["content"])})
        elif raw:
            try:
                payload = _json.loads(raw)
            except _json.JSONDecodeError:
                payload = {}
            if isinstance(payload, list):
                raw_msgs = payload
            elif isinstance(payload, dict):
                raw_msgs = payload.get("messages", [])
            else:
                raw_msgs = []
            for obj in raw_msgs:
                if isinstance(obj, dict) and "role" in obj and "content" in obj:
                    messages.append({"role": str(obj["role"]), "content": str(obj["content"])})

        session_name = path.stem
        config = SessionConfig(
            session_id=str(__import__("uuid").uuid4()),
            name=session_name,
            framework=self._runtime.adapter.framework_name,
            default_model_id="",
        )
        session = await self.create_session(config)

        # Replay messages into the conversation store
        for msg in messages:
            await self._append_message_to_session(session.config.session_id, msg["role"], msg["content"])

        return session

    async def _append_message_to_session(self, session_id: str, role: str, content: str) -> None:
        """Write a message directly into the session's conversation store."""
        import inspect

        runner = self._get_runner(session_id)
        if runner is not None:
            store = runner.get_store()
            if store is not None:
                await store.add_message(role, content)
                return
        adapter = self._runtime.adapter
        if hasattr(adapter, "append_message_to_session"):
            result = adapter.append_message_to_session(session_id, role, content)
            if inspect.isawaitable(result):
                await result

    # ── Model management ──────────────────────────────────────────────────────

    async def set_session_model(self, session_id: str, model_id: str) -> None:
        """Switch the active model for *session_id*."""
        adapter = self._runtime.adapter
        await adapter.set_session_model(session_id, model_id)

    def get_session_model(self, session_id: str) -> str | None:
        """Return the active model ID for *session_id*, or None if unknown."""
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_active_model_id()
        return None

    def get_model_gateway(self) -> Any:
        """Return the model gateway, or None if not configured."""
        return self._model_gateway

    def invalidate_capability_cache(self) -> None:
        """Clear the cached CapabilityRegistry so it is rebuilt on next access."""
        self._capability_registry_cache = None

    def set_session_plan_phase(self, session_id: str, phase: str) -> None:
        """Set the plan phase (``"draft"`` | ``"execute"``) synchronously."""
        runner = self._get_runner(session_id)
        if runner is not None:
            runner.set_plan_phase(phase)

    async def set_session_mode(self, session_id: str, mode_name: str) -> None:
        """Switch the session mode."""
        runner = self._get_runner(session_id)
        if runner is not None:
            await runner.set_mode(mode_name)

    def get_session_mode(self, session_id: str) -> str:
        """Return the active mode name for *session_id*, defaulting to ``"chat"``."""
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_mode()
        return "chat"

    async def set_session_thinking(self, session_id: str, value: bool | None) -> None:
        """Override thinking for *session_id*."""
        runner = self._get_runner(session_id)
        if runner is not None:
            await runner.set_thinking(value)

    def get_session_thinking(self, session_id: str) -> bool | None:
        """Return the thinking override for *session_id* (``None`` = auto)."""
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_thinking()
        return None

    # ── Conversation management ───────────────────────────────────────────────

    def get_conversation_stats(self, session_id: str) -> dict[str, int]:
        """Return message_count, token_estimate, and compaction_count for *session_id*."""
        runner = self._get_runner(session_id)
        if runner is not None:
            stats = runner.get_conversation_stats()
            return {
                "message_count": stats.message_count,
                "token_estimate": stats.token_estimate,
                "compaction_count": stats.compaction_count,
            }
        return {"message_count": 0, "token_estimate": 0, "compaction_count": 0}

    async def compact_conversation(
        self,
        session_id: str,
        keep_recent: int | None = None,
    ) -> int:
        """
        Compact the conversation for *session_id*.

        Generates a model summary when possible; falls back to a plain
        message-count summary when no model is available.

        Returns the number of messages archived (0 if nothing to compact).
        """
        from citnega.packages.config.loaders import load_settings

        settings = load_settings()
        cfg = settings.conversation

        runner = self._get_runner(session_id)
        if runner is None:
            return 0

        keep = keep_recent if keep_recent is not None else cfg.compact_keep_recent

        # Build summary
        if cfg.compact_use_model:
            try:
                summary = await self._generate_compact_summary(runner)
            except Exception:
                summary = self._fallback_compact_summary(runner)
        else:
            summary = self._fallback_compact_summary(runner)

        return await runner.compact(summary, keep_recent=keep)

    async def _generate_compact_summary(self, runner: IFrameworkRunner) -> str:
        """Ask the model to summarise the conversation for compaction."""
        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        messages = runner.get_messages()
        if not messages:
            return self._fallback_compact_summary(runner)

        # Build a condensed transcript
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")[:400]
            lines.append(f"{role}: {content}")
        transcript = "\n".join(lines[-60:])

        summarise_msg = (
            "Please write a concise summary (3-10 sentences) of the conversation above, "
            "capturing the key topics, decisions, and any important context needed to continue "
            "the conversation. Be factual and brief."
        )

        model_id = runner.get_active_model_id()
        if not model_id or self._model_gateway is None:
            return self._fallback_compact_summary(runner)

        req = ModelRequest(
            model_id=model_id,
            messages=[
                ModelMessage(role="system", content="You are a helpful summariser."),
                ModelMessage(
                    role="user",
                    content=f"Conversation transcript:\n\n{transcript}\n\n{summarise_msg}",
                ),
            ],
            temperature=0.3,
            stream=False,
        )
        try:
            response = await self._model_gateway.generate(req)
        except Exception:
            return self._fallback_compact_summary(runner)
        return response.content.strip() or self._fallback_compact_summary(runner)

    @staticmethod
    def _fallback_compact_summary(runner: IFrameworkRunner) -> str:
        stats = runner.get_conversation_stats()
        return f"[Auto-summary] Conversation had {stats.message_count} messages before compaction."

    async def rename_session(self, session_id: str, name: str) -> None:
        """Rename *session_id* to *name* in the session store."""
        try:
            session = await self._runtime.get_session(session_id)
        except Exception:
            return
        new_config = session.config.model_copy(update={"name": name})
        updated = session.model_copy(update={"config": new_config})
        await self._runtime.save_session(updated)

    def _get_runner(self, session_id: str) -> IFrameworkRunner | None:
        """Return the framework runner for *session_id*, or None."""
        runner = self._runtime.get_runner(session_id)
        if runner is not None:
            return runner
        # Also try the adapter (for Direct adapter which keeps its own runner map)
        adapter = self._runtime.adapter
        return adapter.get_runner(session_id)

    # ── Session conversation access ───────────────────────────────────────────

    async def record_tool_call(
        self,
        session_id: str,
        name: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        callable_type: str = "tool",
        msg_count: int | None = None,
    ) -> None:
        """Persist a completed tool/agent call into the session's tool history."""
        runner = self._get_runner(session_id)
        if runner is not None:
            await runner.add_tool_call(
                name, input_summary, output_summary, success,
                callable_type=callable_type, msg_count=msg_count,
            )

    def get_session_tool_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return the stored tool call history for *session_id*."""
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_tool_history()
        # Fallback: disk read when no warm runner is available
        return self._read_conversation_field(session_id, "tool_history")

    def get_conversation_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return the stored message list for *session_id*."""
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_messages()
        # Fallback: disk read when no warm runner is available
        return self._read_conversation_field(session_id, "messages")

    def set_session_skills(self, session_id: str, skill_names: list[str]) -> None:
        from citnega.packages.protocol.events.planning import SkillActivatedEvent

        runner = self._get_runner(session_id)
        if runner is not None:
            runner.set_active_skills(skill_names)
        for skill_name in skill_names:
            self._emitter.emit(
                SkillActivatedEvent(
                    session_id=session_id,
                    run_id=f"skills-{session_id}",
                    skill_name=skill_name,
                    rationale="session_selection",
                )
            )

    def get_session_skills(self, session_id: str) -> list[str]:
        runner = self._get_runner(session_id)
        if runner is not None:
            return runner.get_active_skills()
        return []

    def compile_mental_model(self, session_id: str, text: str) -> dict[str, Any]:
        from citnega.packages.protocol.events.planning import MentalModelCompiledEvent
        from citnega.packages.strategy import compile_mental_model

        spec = compile_mental_model(text)
        runner = self._get_runner(session_id)
        if runner is not None:
            runner.set_mental_model_spec(spec.model_dump())
        self._emitter.emit(
            MentalModelCompiledEvent(
                session_id=session_id,
                run_id=f"mental-model-{session_id}",
                clause_count=len(spec.clauses),
                risk_posture=spec.risk_posture,
                recommended_parallelism=spec.recommended_parallelism,
            )
        )
        return spec.model_dump()

    def list_capabilities(self) -> list[CapabilityDescriptor]:
        return self._build_capability_registry().list_all()

    def list_skills(self) -> list[CapabilityDescriptor]:
        from citnega.packages.capabilities import CapabilityKind

        return self._build_capability_registry().list_by_kind(CapabilityKind.SKILL)

    def invalidate_capability_cache(self) -> None:
        self._capability_registry_cache = None

    def create_dynamic_loader(self) -> Any:
        from citnega.packages.workspace.loader import DynamicLoader

        return DynamicLoader(
            enforcer=self._enforcer,
            emitter=self._emitter,
            tracer=self._tracer,
            tool_registry=self._callable_registry.get_tools(),
        )

    def compile_plan(
        self,
        session_id: str,
        objective: str,
        *,
        capability_id: str | None = None,
        workflow_name: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> CompiledPlan:
        from citnega.packages.capabilities import CapabilityKind
        from citnega.packages.planning import PlanCompiler, PlanValidator
        from citnega.packages.protocol.events.planning import (
            PlanCompiledEvent,
            PlanValidatedEvent,
            WorkflowTemplateExpandedEvent,
        )
        from citnega.packages.strategy import MentalModelSpec, StrategySpec

        registry = self._build_capability_registry()
        runner = self._get_runner(session_id)
        skill_names = runner.get_active_skills() if runner is not None else []
        mode_name = runner.get_mode() if runner is not None else "chat"
        mental_model = runner.get_mental_model_spec() if runner is not None else None
        mental_model_spec = (
            MentalModelSpec.model_validate(mental_model) if mental_model is not None else None
        )
        strategy = StrategySpec(
            mode=mode_name,
            objective=objective,
            active_skills=skill_names,
            parallelism_budget=(
                mental_model_spec.recommended_parallelism if mental_model_spec is not None else 1
            ),
            mental_model_clauses=(
                mental_model_spec.clauses if mental_model_spec is not None else []
            ),
            risk_posture=(
                mental_model_spec.risk_posture if mental_model_spec is not None else "balanced"
            ),
        )

        compiler = PlanCompiler()
        if workflow_name:
            workflow_capability_id = workflow_name
            if workflow_capability_id not in registry:
                workflow_capability_id = f"workflow_template:{workflow_name}"
            descriptor = registry.resolve_descriptor(workflow_capability_id)
            if descriptor.kind != CapabilityKind.WORKFLOW_TEMPLATE:
                raise ValueError(f"{workflow_name!r} is not a workflow template.")
            template = registry.get_runtime(workflow_capability_id)
            plan = compiler.compile_workflow(
                template,
                variables=variables or {},
                strategy=strategy,
                objective=objective,
            )
            self._emitter.emit(
                WorkflowTemplateExpandedEvent(
                    session_id=session_id,
                    run_id=f"plan-{session_id}",
                    plan_id=plan.plan_id,
                    workflow_name=descriptor.display_name,
                    step_count=len(plan.steps),
                )
            )
        else:
            plan = compiler.compile_goal(
                objective,
                strategy=strategy,
                capability_id=capability_id or "conversation_agent",
            )

        validation = PlanValidator().validate(plan, registry)
        synthetic_run_id = f"plan-{session_id}"
        self._emitter.emit(
            PlanCompiledEvent(
                session_id=session_id,
                run_id=synthetic_run_id,
                plan_id=plan.plan_id,
                objective=plan.objective,
                generated_from=plan.generated_from,
                step_count=len(plan.steps),
            )
        )
        self._emitter.emit(
            PlanValidatedEvent(
                session_id=session_id,
                run_id=synthetic_run_id,
                plan_id=plan.plan_id,
                valid=validation.valid,
                errors=validation.errors,
            )
        )
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        if runner is not None:
            runner.set_compiled_plan_metadata(
                {
                    "plan_id": plan.plan_id,
                    "generated_from": plan.generated_from,
                    "objective": plan.objective,
                    "step_count": len(plan.steps),
                }
            )
        return plan

    def _read_conversation_field(self, session_id: str, field: str) -> list[dict[str, Any]]:
        """Read a field from the on-disk conversation.json for *session_id*."""
        adapter = self._runtime.adapter
        return adapter.read_session_conversation_field(session_id, field)

    async def ensure_runner(self, session_id: str) -> None:
        """
        Ensure a framework runner exists for *session_id*.

        Safe to call even if a runner already exists — it is a no-op in that case.
        """
        if self._get_runner(session_id) is not None:
            return
        await self._runtime.ensure_runner(session_id)

    # ── Workspace / hot-reload ────────────────────────────────────────────────

    def register_callable(self, callable_obj: object) -> None:
        """
        Register a callable live (overwriting any previous entry with the same name).

        Registers in both the ApplicationService's local ``_callable_registry``
        and the CoreRuntime's registry so the callable is immediately available
        for tool-calling AND appears in list_tools() / list_agents().
        """
        from citnega.packages.workspace.contract_verifier import verify_callable_contract

        name = getattr(callable_obj, "name", None)
        if not name:
            raise ValueError("Callable has no 'name' attribute.")

        verify_callable_contract(callable_obj)

        # Register in the unified callable registry (both local view and runtime)
        self._callable_registry.register(name, callable_obj, overwrite=True)  # type: ignore[arg-type]
        self._runtime.callable_registry.register(name, callable_obj, overwrite=True)
        self._capability_registry_cache = None

        from citnega.packages.agents.registry import AgentRegistry

        AgentRegistry.wire_core_agents(
            self._callable_registry.get_agents(),
            self._callable_registry.get_tools(),
        )

    async def hot_reload_workfolder(
        self,
        workfolder: Path,
        loader: Any,
    ) -> dict[str, list[str]]:
        """
        Scan *workfolder* for new/changed callables and register them all.

        Returns:
            ``{"registered": [name, ...], "errors": ["name: msg", ...]}``
        """
        from citnega.packages.config.loaders import load_settings
        from citnega.packages.workspace.onboarding import enforce_workspace_onboarding
        from citnega.packages.workspace.writer import WorkspaceWriter

        settings = load_settings(app_home=self._app_home)
        writer = WorkspaceWriter(workfolder)
        enforce_workspace_onboarding(writer.root, settings.workspace)
        workflow_migration: dict[str, list[str]] | None = None
        if settings.nextgen.workflows_enabled:
            from citnega.packages.workspace.workflow_migration import (
                migrate_python_workflows_to_templates,
            )

            workflow_migration = migrate_python_workflows_to_templates(
                writer.workflows_dir
            ).as_dict()
        try:
            loaded_workspace = loader.load_workspace_with_options(
                writer,
                include_python_workflows=not settings.nextgen.workflows_enabled,
            )
        except TypeError:
            loaded_workspace = loader.load_workspace(writer)
        self._capability_registry_cache = None

        registered: list[str] = []
        errors: list[str] = []
        for name, obj in loaded_workspace.ordered_items():
            try:
                self.register_callable(obj)
                registered.append(name)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        refreshed: list[str] = []
        skipped: list[str] = []
        try:
            refresh_result = await self._runtime.refresh_runners()
            refreshed = refresh_result.get("refreshed", [])
            skipped = refresh_result.get("skipped", [])
        except Exception as exc:
            from citnega.packages.observability.logging_setup import runtime_logger as _log
            _log.warning("workspace_runner_refresh_failed", error=str(exc))

        result: dict[str, Any] = {
            "registered": registered,
            "errors": errors,
            "refreshed_sessions": refreshed,
            "skipped_sessions": skipped,
        }
        if workflow_migration is not None:
            result["workflow_migration"] = workflow_migration
        return result

    def save_workspace_path(self, path: str) -> None:
        """Persist *path* as the workfolder in ``<app_home>/config/workspace.toml``."""
        if self._app_home is not None:
            from citnega.packages.config.loaders import save_workspace_settings

            save_workspace_settings(path, self._app_home)
            self._capability_registry_cache = None

    # ── Registry queries ───────────────────────────────────────────────────────

    def list_agents(self) -> list[CallableMetadata]:
        return [v.get_metadata() for v in self._callable_registry.get_agents().values()]

    def list_tools(self) -> list[CallableMetadata]:
        return [v.get_metadata() for v in self._callable_registry.get_tools().values()]

    def list_frameworks(self) -> list[str]:
        return [self._runtime.adapter.framework_name]

    def list_models(self) -> list[ModelInfo]:
        # 1. Prefer adapter-owned model catalog when available
        adapter = self._runtime.adapter
        with contextlib.suppress(Exception):
            adapter_models = adapter.list_models()
            if adapter_models:
                return adapter_models

        # 2. Injected model gateway
        if self._model_gateway is not None:
            try:
                models = self._model_gateway.list_models()
                if asyncio.iscoroutine(models):
                    return []
                return list(models)
            except Exception as exc:
                from citnega.packages.observability.logging_setup import runtime_logger as _log
                _log.warning("model_gateway_list_models_failed", error=str(exc))

        # 3. Fallback: load directly from the bundled model_registry.toml
        try:
            from citnega.packages.model_gateway.registry import ModelRegistry

            reg = ModelRegistry()
            reg.load()
            return list(reg.list_all())
        except Exception:
            return []

    def _build_capability_registry(self) -> CapabilityRegistry:
        from citnega.packages.capabilities import (
            BuiltinCapabilityProvider,
            CapabilityKind,
            CapabilityRegistry,
            WorkspaceCapabilityProvider,
        )
        from citnega.packages.capabilities.providers import MentalModelCapabilityProvider
        from citnega.packages.config.loaders import load_settings
        from citnega.packages.protocol.events.planning import CapabilityLoadFailedEvent

        if self._capability_registry_cache is not None:
            return self._capability_registry_cache

        # Seed from the runtime's pre-built capability registry when available
        # (avoids redundant BuiltinCapabilityProvider scan at runtime).
        _runtime_attr = getattr(self._runtime, "capability_registry", None)
        runtime_cap_reg = _runtime_attr if isinstance(_runtime_attr, CapabilityRegistry) else None
        registry = runtime_cap_reg if runtime_cap_reg is not None else CapabilityRegistry()

        if runtime_cap_reg is None:
            # Runtime registry was not pre-built — build builtins now.
            callables = {item.name: item for item in self._callable_registry.list_all()}
            builtin_records, builtin_diagnostics = BuiltinCapabilityProvider().load(callables)
            for failure in builtin_diagnostics.failures:
                self._emitter.emit(
                    CapabilityLoadFailedEvent(
                        session_id="system",
                        run_id="capability-bootstrap",
                        capability_id=failure.capability_id,
                        source=failure.source,
                        path=failure.path,
                        error=failure.error,
                        required=failure.required,
                    )
                )
            if builtin_diagnostics.has_required_failures:
                details = "; ".join(
                    f"{failure.capability_id}: {failure.error}"
                    for failure in builtin_diagnostics.failures
                )
                raise RuntimeError(f"Capability bootstrap failed: {details}")
            registry.register_many(builtin_records, overwrite=True)

        settings = load_settings(app_home=self._app_home)
        workspace_root = (
            Path(settings.workspace.workfolder_path).expanduser()
            if settings.workspace.workfolder_path
            else None
        )
        workspace_records, workspace_diagnostics = WorkspaceCapabilityProvider(workspace_root).load()
        for failure in workspace_diagnostics.failures:
            self._emitter.emit(
                CapabilityLoadFailedEvent(
                    session_id="system",
                    run_id="capability-bootstrap",
                    capability_id=failure.capability_id,
                    source=failure.source,
                    path=failure.path,
                    error=failure.error,
                    required=failure.required,
                )
            )
        for record in workspace_records:
            if record.descriptor.kind == CapabilityKind.SKILL and not settings.nextgen.skills_enabled:
                continue
            if (
                record.descriptor.kind == CapabilityKind.WORKFLOW_TEMPLATE
                and not settings.nextgen.workflows_enabled
            ):
                continue
            registry.register(record, overwrite=True)
        # Load mental models from workspace
        mm_records, mm_diagnostics = MentalModelCapabilityProvider(workspace_root).load()
        for failure in mm_diagnostics.failures:
            self._emitter.emit(
                CapabilityLoadFailedEvent(
                    session_id="system",
                    run_id="capability-bootstrap",
                    capability_id=failure.capability_id,
                    source=failure.source,
                    path=failure.path,
                    error=failure.error,
                    required=failure.required,
                )
            )
        for record in mm_records:
            registry.register(record, overwrite=True)

        self._capability_registry_cache = registry
        return registry
