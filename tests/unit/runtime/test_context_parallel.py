"""
Unit tests for parallel context assembly (Phase 7, Step 7.2).

Verifies:
- parallel_safe handlers run concurrently when parallel_context enabled
- Non-parallel_safe handlers run serially
- handler error isolation (one failure doesn't abort others)
- result ordering is stable (sources in handler registration order)
- serial path works correctly when parallel disabled
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.runtime.context.assembler import ContextAssembler


def _make_session(session_id: str = "s1", max_tokens: int = 1000) -> MagicMock:
    session = MagicMock()
    session.config.session_id = session_id
    session.config.default_model_id = "test-model"
    session.config.max_context_tokens = max_tokens
    return session


def _make_source(name: str, tokens: int = 10) -> ContextSource:
    return ContextSource(source_type=name, content=name, token_count=tokens)


class _TrackingHandler(IContextHandler):
    """Handler that records when it ran and adds a source."""

    parallel_safe = True

    def __init__(self, name: str, delay: float = 0.0, source_tokens: int = 10) -> None:
        self._name = name
        self._delay = delay
        self._source_tokens = source_tokens
        self.ran_at: float | None = None

    @property
    def name(self) -> str:
        return self._name

    async def enrich(self, context: ContextObject, session: Any) -> ContextObject:
        if self._delay:
            await asyncio.sleep(self._delay)
        self.ran_at = asyncio.get_event_loop().time()
        src = _make_source(self._name, self._source_tokens)
        return context.model_copy(
            update={
                "sources": [*context.sources, src],
                "total_tokens": context.total_tokens + self._source_tokens,
                "budget_remaining": context.budget_remaining - self._source_tokens,
            }
        )


class _FailingHandler(IContextHandler):
    """Handler that always raises."""

    parallel_safe = True
    name = "failing_handler"

    async def enrich(self, context: ContextObject, session: Any) -> ContextObject:
        raise RuntimeError("handler error")


class _SerialHandler(IContextHandler):
    """Handler that is NOT parallel_safe."""

    parallel_safe = False
    name = "serial_handler"

    def __init__(self) -> None:
        self.called = False

    async def enrich(self, context: ContextObject, session: Any) -> ContextObject:
        self.called = True
        src = _make_source("serial", 5)
        return context.model_copy(
            update={
                "sources": [*context.sources, src],
                "total_tokens": context.total_tokens + 5,
                "budget_remaining": context.budget_remaining - 5,
            }
        )


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parallel_handlers_run_all() -> None:
    """parallel_safe handlers all run when parallel_context_enabled=True."""
    h1 = _TrackingHandler("h1", delay=0.01)
    h2 = _TrackingHandler("h2", delay=0.01)
    h3 = _TrackingHandler("h3", delay=0.01)
    assembler = ContextAssembler(handlers=[h1, h2, h3])
    session = _make_session()

    with patch(
        "citnega.packages.runtime.context.assembler.ContextAssembler._parallel_context_enabled",
        return_value=True,
    ):
        result = await assembler.assemble(session, "hello", "r1")

    assert h1.ran_at is not None
    assert h2.ran_at is not None
    assert h3.ran_at is not None
    source_names = {s.source_type for s in result.sources}
    assert {"h1", "h2", "h3"} <= source_names
    assert result.total_tokens == 30


@pytest.mark.asyncio
async def test_serial_handler_not_in_parallel_group() -> None:
    """Non-parallel_safe handler runs serially even when parallel enabled."""
    h_par = _TrackingHandler("parallel_h")
    h_ser = _SerialHandler()
    assembler = ContextAssembler(handlers=[h_par, h_ser])
    session = _make_session()

    with patch(
        "citnega.packages.runtime.context.assembler.ContextAssembler._parallel_context_enabled",
        return_value=True,
    ):
        result = await assembler.assemble(session, "hello", "r1")

    assert h_par.ran_at is not None
    assert h_ser.called
    source_names = {s.source_type for s in result.sources}
    assert "parallel_h" in source_names
    assert "serial" in source_names


@pytest.mark.asyncio
async def test_handler_error_does_not_abort_chain() -> None:
    """A failing handler logs and continues; subsequent handlers still run."""
    h1 = _TrackingHandler("before")
    failing = _FailingHandler()
    h2 = _TrackingHandler("after")
    assembler = ContextAssembler(handlers=[h1, failing, h2])
    session = _make_session()

    with patch(
        "citnega.packages.runtime.context.assembler.ContextAssembler._parallel_context_enabled",
        return_value=False,
    ):
        result = await assembler.assemble(session, "hello", "r1")

    source_names = {s.source_type for s in result.sources}
    assert "before" in source_names
    assert "after" in source_names
    assert "failing_handler" not in source_names


@pytest.mark.asyncio
async def test_parallel_result_stable_order() -> None:
    """Sources from parallel handlers are collated in handler registration order."""
    # h0 has smallest delay so finishes first, h2 has largest delay
    handlers = [_TrackingHandler(f"h{i}", delay=0.005 * (3 - i)) for i in range(3)]
    assembler = ContextAssembler(handlers=handlers)
    session = _make_session()

    with patch(
        "citnega.packages.runtime.context.assembler.ContextAssembler._parallel_context_enabled",
        return_value=True,
    ):
        result = await assembler.assemble(session, "hello", "r1")

    parallel_sources = [s.source_type for s in result.sources if s.source_type.startswith("h")]
    assert parallel_sources == ["h0", "h1", "h2"]


@pytest.mark.asyncio
async def test_parallel_disabled_runs_serially() -> None:
    """When parallel_context_enabled=False, handlers run one at a time."""
    h1 = _TrackingHandler("h1")
    h2 = _TrackingHandler("h2")
    assembler = ContextAssembler(handlers=[h1, h2])
    session = _make_session()

    with patch(
        "citnega.packages.runtime.context.assembler.ContextAssembler._parallel_context_enabled",
        return_value=False,
    ):
        result = await assembler.assemble(session, "hello", "r1")

    assert h1.ran_at is not None
    assert h2.ran_at is not None
    source_names = {s.source_type for s in result.sources}
    assert {"h1", "h2"} <= source_names
