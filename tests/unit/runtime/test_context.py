"""Unit tests for ContextAssembler and its handlers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.protocol.models.messages import Message, MessageRole
from citnega.packages.protocol.models.runs import RunState, RunSummary, StateSnapshot
from citnega.packages.protocol.models.sessions import Session, SessionConfig
from citnega.packages.runtime.context.assembler import ContextAssembler
from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler
from citnega.packages.runtime.context.handlers.recent_turns import RecentTurnsHandler
from citnega.packages.runtime.context.handlers.runtime_state import RuntimeStateHandler
from citnega.packages.runtime.context.handlers.session_summary import SessionSummaryHandler
from citnega.packages.runtime.context.handlers.token_budget import TokenBudgetHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def _session(max_context_tokens: int = 8192, kb_enabled: bool = True) -> Session:
    cfg = SessionConfig(
        session_id="sess-1",
        name="test session",
        framework="adk",
        default_model_id="model-x",
        max_context_tokens=max_context_tokens,
        kb_enabled=kb_enabled,
    )
    return Session(config=cfg, created_at=_NOW, last_active_at=_NOW)


def _empty_context(session: Session, budget: int | None = None) -> ContextObject:
    b = budget if budget is not None else session.config.max_context_tokens
    return ContextObject(
        session_id=session.config.session_id,
        run_id="run-1",
        user_input="Hello",
        assembled_at=_NOW,
        budget_remaining=b,
    )


def _message(role: MessageRole, content: str) -> Message:
    return Message(
        message_id="msg-1",
        session_id="sess-1",
        role=role,
        content=content,
        timestamp=_NOW,
    )


def _run_summary(state: RunState = RunState.COMPLETED) -> RunSummary:
    return RunSummary(
        run_id="run-old",
        session_id="sess-1",
        started_at=_NOW,
        state=state,
        turn_count=2,
        total_tokens=100,
    )


# ---------------------------------------------------------------------------
# RecentTurnsHandler
# ---------------------------------------------------------------------------


class TestRecentTurnsHandler:
    @pytest.mark.asyncio
    async def test_adds_source(self) -> None:
        repo = AsyncMock()
        repo.list.return_value = [
            _message(MessageRole.USER, "hi"),
            _message(MessageRole.ASSISTANT, "hello"),
        ]
        handler = RecentTurnsHandler(repo, recent_turns_count=10)
        session = _session()
        ctx = await handler.enrich(_empty_context(session), session)
        assert len(ctx.sources) == 1
        assert ctx.sources[0].source_type == "recent_turns"
        assert "USER" in ctx.sources[0].content
        assert ctx.total_tokens > 0

    @pytest.mark.asyncio
    async def test_empty_messages_no_source(self) -> None:
        repo = AsyncMock()
        repo.list.return_value = []
        handler = RecentTurnsHandler(repo)
        session = _session()
        ctx = await handler.enrich(_empty_context(session), session)
        assert ctx.sources == []


# ---------------------------------------------------------------------------
# SessionSummaryHandler
# ---------------------------------------------------------------------------


class TestSessionSummaryHandler:
    @pytest.mark.asyncio
    async def test_adds_summary_source(self) -> None:
        repo = AsyncMock()
        repo.list.return_value = [_run_summary(), _run_summary(RunState.FAILED)]
        handler = SessionSummaryHandler(repo)
        session = _session()
        ctx = await handler.enrich(_empty_context(session), session)
        assert len(ctx.sources) == 1
        assert ctx.sources[0].source_type == "summary"
        assert "ok" in ctx.sources[0].content

    @pytest.mark.asyncio
    async def test_no_runs_returns_unchanged(self) -> None:
        repo = AsyncMock()
        repo.list.return_value = []
        handler = SessionSummaryHandler(repo)
        session = _session()
        ctx = await handler.enrich(_empty_context(session), session)
        assert ctx.sources == []


# ---------------------------------------------------------------------------
# KBRetrievalHandler (stub)
# ---------------------------------------------------------------------------


class TestKBRetrievalHandler:
    @pytest.mark.asyncio
    async def test_stub_passthrough(self) -> None:
        # No kb_store → handler is a pass-through
        handler = KBRetrievalHandler(kb_store=None)
        session = _session(kb_enabled=True)
        ctx = _empty_context(session)
        result = await handler.enrich(ctx, session)
        assert result is ctx  # unchanged reference

    @pytest.mark.asyncio
    async def test_disabled_passthrough(self) -> None:
        # No kb_store → handler is always a pass-through
        handler = KBRetrievalHandler(kb_store=None)
        session = _session(kb_enabled=False)
        ctx = _empty_context(session)
        result = await handler.enrich(ctx, session)
        assert result is ctx


# ---------------------------------------------------------------------------
# RuntimeStateHandler
# ---------------------------------------------------------------------------


class TestRuntimeStateHandler:
    @pytest.mark.asyncio
    async def test_no_snapshot_returns_unchanged(self) -> None:
        handler = RuntimeStateHandler()
        session = _session()
        ctx = _empty_context(session)
        result = await handler.enrich(ctx, session)
        assert result is ctx

    @pytest.mark.asyncio
    async def test_snapshot_adds_state_source(self) -> None:
        handler = RuntimeStateHandler()
        handler.set_snapshot(
            StateSnapshot(
                session_id="sess-1",
                current_run_id="run-1",
                active_callable=None,
                run_state=RunState.EXECUTING,
                context_token_count=100,
                checkpoint_available=False,
                framework_name="adk",
                captured_at=_NOW,
            )
        )
        session = _session()
        ctx = await handler.enrich(_empty_context(session), session)
        assert len(ctx.sources) == 1
        assert ctx.sources[0].source_type == "state"
        assert "executing" in ctx.sources[0].content


# ---------------------------------------------------------------------------
# TokenBudgetHandler
# ---------------------------------------------------------------------------


class TestTokenBudgetHandler:
    @pytest.mark.asyncio
    async def test_within_budget_no_truncation(self) -> None:
        handler = TokenBudgetHandler(max_context_tokens=1000)
        session = _session(max_context_tokens=1000)
        # 10 token source
        source = ContextSource(source_type="recent_turns", content="x" * 40, token_count=10)
        ctx = _empty_context(session).model_copy(update={"sources": [source], "total_tokens": 10})
        result = await handler.enrich(ctx, session)
        assert not result.truncated
        assert len(result.sources) == 1

    @pytest.mark.asyncio
    async def test_over_budget_drops_low_priority(self) -> None:
        handler = TokenBudgetHandler(max_context_tokens=100)
        session = _session(max_context_tokens=100)
        # High priority (recent_turns=100) + low priority (kb=40)
        high = ContextSource(source_type="recent_turns", content="A" * 160, token_count=40)
        low = ContextSource(source_type="kb", content="B" * 320, token_count=80)
        ctx = _empty_context(session, budget=100).model_copy(
            update={"sources": [high, low], "total_tokens": 120}
        )
        result = await handler.enrich(ctx, session)
        assert result.truncated
        source_types = [s.source_type for s in result.sources]
        assert "recent_turns" in source_types
        assert "kb" not in source_types

    @pytest.mark.asyncio
    async def test_empty_sources_no_error(self) -> None:
        handler = TokenBudgetHandler()
        session = _session()
        ctx = _empty_context(session)
        result = await handler.enrich(ctx, session)
        assert not result.truncated


# ---------------------------------------------------------------------------
# ContextAssembler (full chain)
# ---------------------------------------------------------------------------


class TestContextAssembler:
    @pytest.mark.asyncio
    async def test_chain_runs_all_handlers(self) -> None:
        call_order: list[str] = []

        class TrackingHandler:
            def __init__(self, n: str) -> None:
                self._name = n

            @property
            def name(self) -> str:
                return self._name

            async def enrich(self, ctx: ContextObject, session: Session) -> ContextObject:
                call_order.append(self._name)
                return ctx

        assembler = ContextAssembler(
            [
                TrackingHandler("a"),
                TrackingHandler("b"),
                TrackingHandler("c"),
            ]
        )
        session = _session()
        await assembler.assemble(session, "hello", "run-1")
        assert call_order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_broken_handler_skipped(self) -> None:
        class OkHandler:
            @property
            def name(self) -> str:
                return "ok"

            async def enrich(self, ctx: ContextObject, session: Session) -> ContextObject:
                return ctx.model_copy(
                    update={
                        "sources": [
                            *ctx.sources,
                            ContextSource(source_type="ok", content="x", token_count=1),
                        ]
                    }
                )

        class BrokenHandler:
            @property
            def name(self) -> str:
                return "broken"

            async def enrich(self, ctx: ContextObject, session: Session) -> ContextObject:
                raise RuntimeError("DB gone")

        assembler = ContextAssembler([BrokenHandler(), OkHandler()])
        session = _session()
        ctx = await assembler.assemble(session, "hello", "run-1")
        # OkHandler still ran despite BrokenHandler failing
        assert any(s.source_type == "ok" for s in ctx.sources)

    def test_empty_handler_list_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one handler"):
            ContextAssembler([])

    @pytest.mark.asyncio
    async def test_full_chain_integration(self) -> None:
        """Smoke test: all real handlers wired together."""
        msg_repo = AsyncMock()
        msg_repo.list.return_value = [_message(MessageRole.USER, "test")]
        run_repo = AsyncMock()
        run_repo.list.return_value = [_run_summary()]

        state_handler = RuntimeStateHandler()
        state_handler.set_snapshot(
            StateSnapshot(
                session_id="sess-1",
                current_run_id="run-1",
                active_callable=None,
                run_state=RunState.EXECUTING,
                context_token_count=50,
                checkpoint_available=False,
                framework_name="adk",
                captured_at=_NOW,
            )
        )

        assembler = ContextAssembler(
            [
                RecentTurnsHandler(msg_repo, recent_turns_count=10),
                SessionSummaryHandler(run_repo),
                KBRetrievalHandler(),
                state_handler,
                TokenBudgetHandler(max_context_tokens=8192),
            ]
        )

        session = _session()
        ctx = await assembler.assemble(session, "What is the weather?", "run-1")

        assert ctx.session_id == "sess-1"
        assert ctx.run_id == "run-1"
        assert not ctx.truncated
        source_types = {s.source_type for s in ctx.sources}
        assert "recent_turns" in source_types
        assert "summary" in source_types
        assert "state" in source_types

    @pytest.mark.asyncio
    async def test_parallel_safe_handlers_merge_in_handler_order(self) -> None:
        class ParallelHandler:
            parallel_safe = True

            def __init__(self, name: str, delay: float) -> None:
                self._name = name
                self._delay = delay

            @property
            def name(self) -> str:
                return self._name

            async def enrich(self, ctx: ContextObject, session: Session) -> ContextObject:
                await asyncio.sleep(self._delay)
                source = ContextSource(source_type=self._name, content=self._name, token_count=1)
                return ctx.model_copy(
                    update={
                        "sources": [*ctx.sources, source],
                        "total_tokens": ctx.total_tokens + 1,
                        "budget_remaining": ctx.budget_remaining - 1,
                    }
                )

        settings = MagicMock()
        settings.nextgen.parallel_execution_enabled = True
        with patch("citnega.packages.config.loaders.load_settings", return_value=settings):
            assembler = ContextAssembler(
                [ParallelHandler("first", 0.03), ParallelHandler("second", 0.01)]
            )
            ctx = await assembler.assemble(_session(), "hello", "run-1")

        assert [source.source_type for source in ctx.sources] == ["first", "second"]

    @pytest.mark.asyncio
    async def test_token_budget_emits_context_truncated_event(self) -> None:
        from unittest.mock import MagicMock
        from citnega.packages.protocol.events.context import ContextTruncatedEvent

        emitter = MagicMock()
        emitted: list[object] = []
        emitter.emit.side_effect = emitted.append

        handler = TokenBudgetHandler(max_context_tokens=50, emitter=emitter)
        session = _session(max_context_tokens=50)
        high = ContextSource(source_type="recent_turns", content="A" * 80, token_count=20)
        low = ContextSource(source_type="kb", content="B" * 200, token_count=60)
        ctx = _empty_context(session, budget=50).model_copy(
            update={"sources": [high, low], "total_tokens": 80}
        )
        result = await handler.enrich(ctx, session)
        assert result.truncated
        truncated_events = [e for e in emitted if isinstance(e, ContextTruncatedEvent)]
        assert len(truncated_events) == 1
        assert "kb" in truncated_events[0].dropped_sources
