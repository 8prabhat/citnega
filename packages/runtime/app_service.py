"""
ApplicationService — IApplicationService facade over CoreRuntime.

This is the single object that CLI and TUI depend on.  Nothing here imports
framework adapters, storage drivers, or infrastructure directly — all of that
is injected at construction time by the bootstrap (Phase 9) or the lightweight
CLI bootstrap (Phase 6).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from citnega.packages.protocol.callables.types import CallableMetadata
from citnega.packages.protocol.events import CanonicalEvent
from citnega.packages.protocol.events.lifecycle import RunCompleteEvent
from citnega.packages.protocol.interfaces.application_service import IApplicationService
from citnega.packages.protocol.models import (
    KBItem,
    KBSearchResult,
    ModelInfo,
    RunSummary,
    Session,
    SessionConfig,
    StateSnapshot,
)
from citnega.packages.protocol.models.approvals import ApprovalStatus
from citnega.packages.runtime.core_runtime import CoreRuntime
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.policy.approval_manager import ApprovalManager

# ── sentinel ──────────────────────────────────────────────────────────────────
_STREAM_TIMEOUT = 60.0   # seconds to wait for the next event before giving up


class ApplicationService(IApplicationService):
    """
    Concrete IApplicationService.

    Only the constructor touches runtime internals; every public method uses
    the injected interface.  KB, export/import, and model list are stubs until
    Phase 8 / Phase 9.
    """

    def __init__(
        self,
        runtime: CoreRuntime,
        emitter: EventEmitter,
        approval_manager: ApprovalManager,
        *,
        model_gateway=None,    # IModelGateway | None
        kb_store=None,         # IKnowledgeStore | None — None until Phase 8 wiring
        tool_registry: dict | None = None,
        agent_registry: dict | None = None,
    ) -> None:
        self._runtime          = runtime
        self._emitter          = emitter
        self._approval_manager = approval_manager
        self._model_gateway    = model_gateway
        self._kb_store         = kb_store
        self._tool_registry    = tool_registry or {}
        self._agent_registry   = agent_registry or {}

    # ── Session management ─────────────────────────────────────────────────────

    async def create_session(self, config: SessionConfig) -> Session:
        return await self._runtime.create_session(config)

    async def get_session(self, session_id: str) -> Session | None:
        try:
            return await self._runtime._sessions.get(session_id)
        except Exception:
            return None

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        all_sessions = await self._runtime._sessions.list_all()
        return all_sessions[:limit]

    async def delete_session(self, session_id: str) -> None:
        await self._runtime._sessions.delete(session_id)

    # ── Run execution ──────────────────────────────────────────────────────────

    async def run_turn(self, session_id: str, user_input: str) -> str:
        run_id = await self._runtime.run_turn(session_id, user_input)

        # Auto-compact if thresholds are exceeded
        try:
            await self._maybe_auto_compact(session_id)
        except Exception:
            pass  # auto-compact failure must never surface to the user

        # Auto-rename new session from first user message
        try:
            await self._maybe_auto_rename(session_id, user_input)
        except Exception:
            pass

        return run_id

    async def _maybe_auto_compact(self, session_id: str) -> None:
        """Trigger compaction when configured thresholds are exceeded."""
        from citnega.packages.config.loaders import load_settings  # noqa: PLC0415
        settings = load_settings()
        cfg = settings.conversation

        if not cfg.auto_compact:
            return

        stats = self.get_conversation_stats(session_id)
        msg_over   = cfg.compact_threshold_messages > 0 and stats["message_count"]   >= cfg.compact_threshold_messages
        token_over = cfg.compact_threshold_tokens   > 0 and stats["token_estimate"]  >= cfg.compact_threshold_tokens

        if msg_over or token_over:
            from citnega.packages.observability.logging_setup import runtime_logger  # noqa: PLC0415
            runtime_logger.info(
                "auto_compact_triggered",
                session_id=session_id,
                message_count=stats["message_count"],
                token_estimate=stats["token_estimate"],
            )
            await self.compact_conversation(session_id)

    async def _maybe_auto_rename(self, session_id: str, user_input: str) -> None:
        """Rename a brand-new session to the first user message text."""
        from citnega.packages.config.loaders import load_settings  # noqa: PLC0415
        settings = load_settings()
        if not settings.conversation.auto_name_from_first_message:
            return

        stats = self.get_conversation_stats(session_id)
        if stats["message_count"] != 2:   # user + assistant = first turn
            return

        try:
            session = await self._runtime._session_manager.get(session_id)
        except Exception:
            return

        # Only rename if it still has the default placeholder name
        if session.config.name not in ("new-session", "tui-session", "bootstrap-test", "turn-test"):
            return

        # Derive a short name from the first message
        name = user_input.strip().splitlines()[0][:60] or "session"
        await self.rename_session(session_id, name)

    async def stream_events(self, run_id: str) -> AsyncIterator[CanonicalEvent]:  # type: ignore[override]
        """
        Async generator: yields events for *run_id* until RunCompleteEvent
        arrives or the stream times out.

        Usage::

            async for event in svc.stream_events(run_id):
                ...
        """
        queue = self._emitter.get_queue(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_STREAM_TIMEOUT)
                except asyncio.TimeoutError:
                    break
                yield event
                if isinstance(event, RunCompleteEvent):
                    break
        finally:
            # Consumer owns queue cleanup — safe to remove now that we're done.
            self._emitter.close_queue(run_id)

    async def get_run(self, run_id: str) -> RunSummary | None:
        try:
            return await self._runtime._runs.get(run_id)
        except Exception:
            return None

    async def list_runs(self, session_id: str, limit: int = 50) -> list[RunSummary]:
        return await self._runtime._runs.list_for_session(session_id, limit=limit)

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

    async def export_session(self, session_id: str) -> Path:
        """Export KB items for *session_id* to JSONL.  Full export in Phase 9."""
        if self._kb_store is None:
            raise NotImplementedError("Session export requires a KB store (Phase 9).")
        return await self._kb_store.export_all()

    async def import_session(self, path: Path) -> Session:
        raise NotImplementedError("Session import is not yet available (Phase 9).")

    # ── Model management ──────────────────────────────────────────────────────

    async def set_session_model(self, session_id: str, model_id: str) -> None:
        """
        Switch the active model for *session_id*.

        Delegates to the adapter if it supports per-session model switching
        (e.g. DirectModelAdapter).  Silently no-ops otherwise.
        """
        adapter = self._runtime._adapter
        if hasattr(adapter, "set_session_model"):
            await adapter.set_session_model(session_id, model_id)

    def get_session_model(self, session_id: str) -> str | None:
        """Return the active model ID for *session_id*, or None if unknown."""
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "_conv"):
            return runner._conv.active_model_id
        return None

    def set_session_plan_phase(self, session_id: str, phase: str) -> None:
        """Set the plan phase (``"draft"`` | ``"execute"``) synchronously."""
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "set_plan_phase"):
            runner.set_plan_phase(phase)

    async def set_session_mode(self, session_id: str, mode_name: str) -> None:
        """
        Switch the session mode (``"chat"`` | ``"plan"`` | ``"explore"``).

        Delegates to the runner so the mode is persisted in ConversationStore.
        Silently no-ops for adapters that do not support modes.
        """
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "set_mode"):
            await runner.set_mode(mode_name)

    def get_session_mode(self, session_id: str) -> str:
        """Return the active mode name for *session_id*, defaulting to ``"chat"``."""
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "_conv"):
            return runner._conv.mode_name
        return "chat"

    async def set_session_thinking(self, session_id: str, value: bool | None) -> None:
        """
        Override thinking for *session_id*.

        ``True`` = force on, ``False`` = force off, ``None`` = auto (model YAML default).
        """
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "set_thinking"):
            await runner.set_thinking(value)

    def get_session_thinking(self, session_id: str) -> bool | None:
        """Return the thinking override for *session_id* (``None`` = auto)."""
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "get_thinking"):
            return runner.get_thinking()
        return None

    # ── Conversation management ───────────────────────────────────────────────

    def get_conversation_stats(self, session_id: str) -> dict:
        """Return message_count, token_estimate, and compaction_count for *session_id*."""
        runner = self._get_runner(session_id)
        if runner is not None and hasattr(runner, "_conv"):
            conv = runner._conv
            return {
                "message_count":    conv.message_count,
                "token_estimate":   conv.token_estimate,
                "compaction_count": conv.compaction_count,
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
        from citnega.packages.config.loaders import load_settings  # noqa: PLC0415
        settings = load_settings()
        cfg = settings.conversation

        runner = self._get_runner(session_id)
        if runner is None or not hasattr(runner, "_conv"):
            return 0

        conv = runner._conv
        keep = keep_recent if keep_recent is not None else cfg.compact_keep_recent

        # Build summary
        if cfg.compact_use_model:
            try:
                summary = await self._generate_compact_summary(runner, conv)
            except Exception:
                summary = self._fallback_compact_summary(conv)
        else:
            summary = self._fallback_compact_summary(conv)

        return await conv.compact(summary, keep_recent=keep)

    async def _generate_compact_summary(self, runner, conv) -> str:
        """Ask the model to summarise the conversation for compaction."""
        from citnega.packages.model_gateway.provider_factory import ProviderFactory  # noqa: PLC0415
        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest  # noqa: PLC0415

        messages = conv.get_messages()
        if not messages:
            return self._fallback_compact_summary(conv)

        # Build a condensed transcript
        lines = []
        for m in messages:
            role    = m.get("role", "?")
            content = m.get("content", "")[:400]  # truncate long messages
            lines.append(f"{role}: {content}")
        transcript = "\n".join(lines[-60:])  # cap at last 60 messages

        summarise_msg = (
            "Please write a concise summary (3-10 sentences) of the conversation above, "
            "capturing the key topics, decisions, and any important context needed to continue "
            "the conversation. Be factual and brief."
        )

        model_id = conv.active_model_id
        factory  = runner._factory
        try:
            provider, _ = runner._resolve_provider(model_id)
        except Exception:
            return self._fallback_compact_summary(conv)

        req = ModelRequest(
            model_id=model_id,
            messages=[
                ModelMessage(role="system",    content="You are a helpful summariser."),
                ModelMessage(role="user",      content=f"Conversation transcript:\n\n{transcript}\n\n{summarise_msg}"),
            ],
            stream=False,
            temperature=0.3,
        )
        full_text: list[str] = []
        async for chunk in provider.stream_generate(req):
            if chunk.content:
                full_text.append(chunk.content)
        return "".join(full_text).strip() or self._fallback_compact_summary(conv)

    @staticmethod
    def _fallback_compact_summary(conv) -> str:
        count = conv.message_count
        return f"[Auto-summary] Conversation had {count} messages before compaction."

    async def rename_session(self, session_id: str, name: str) -> None:
        """Rename *session_id* to *name* in the session store."""
        try:
            session = await self._runtime._session_manager.get(session_id)
        except Exception:
            return
        new_config = session.config.model_copy(update={"name": name})
        updated    = session.model_copy(update={"config": new_config})
        await self._runtime._session_manager._repo.save(updated)

    def _get_runner(self, session_id: str):
        """Return the framework runner for *session_id*, or None."""
        adapter = self._runtime._adapter
        if hasattr(adapter, "get_runner"):
            return adapter.get_runner(session_id)
        return None

    # ── Registry queries ───────────────────────────────────────────────────────

    def list_agents(self) -> list[CallableMetadata]:
        return [
            v.get_metadata()
            for v in self._agent_registry.values()
            if hasattr(v, "get_metadata")
        ]

    def list_tools(self) -> list[CallableMetadata]:
        return [
            v.get_metadata()
            for v in self._tool_registry.values()
            if hasattr(v, "get_metadata")
        ]

    def list_frameworks(self) -> list[str]:
        return [self._runtime._adapter.framework_name]

    def list_models(self) -> list[ModelInfo]:
        # 1. Prefer YAML-driven config from DirectModelAdapter
        adapter = self._runtime._adapter
        if hasattr(adapter, "_yaml_config"):
            try:
                from citnega.packages.model_gateway.provider_factory import _make_model_info  # noqa: PLC0415
                return [
                    _make_model_info(entry)
                    for entry in sorted(adapter._yaml_config.models, key=lambda m: -m.priority)
                ]
            except Exception:
                pass

        # 2. Injected model gateway
        if self._model_gateway is not None:
            try:
                return list(self._model_gateway._registry.list_all())
            except Exception:
                pass

        # 3. Fallback: load directly from the bundled model_registry.toml
        try:
            from citnega.packages.model_gateway.registry import ModelRegistry  # noqa: PLC0415
            reg = ModelRegistry()
            reg.load()
            return list(reg.list_all())
        except Exception:
            return []
