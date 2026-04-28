"""
Unit tests for Batch 1/7 TraceSpan, SpanRepository, and Tracer span wiring.
"""

from __future__ import annotations

import asyncio
from dataclasses import fields
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_trace_span_dataclass_fields():
    from citnega.packages.runtime.tracing.span import TraceSpan
    field_names = {f.name for f in fields(TraceSpan)}
    required = {
        "span_id", "run_id", "turn_id", "step_id",
        "tool_name", "start_ts", "end_ts",
        "input_hash", "output_hash", "success",
    }
    assert required.issubset(field_names)


def test_trace_span_instantiation():
    from citnega.packages.runtime.tracing.span import TraceSpan
    span = TraceSpan(
        span_id="sp1",
        run_id="r1",
        turn_id="t1",
        step_id=None,
        tool_name="my_tool",
        start_ts="2024-01-01T00:00:00Z",
        end_ts="2024-01-01T00:00:01Z",
        input_hash="abc123",
        output_hash="def456",
        success=True,
    )
    assert span.span_id == "sp1"
    assert span.success is True


@pytest.mark.asyncio
async def test_span_repository_save_and_list(tmp_db):
    from citnega.packages.runtime.tracing.span import TraceSpan
    from citnega.packages.runtime.tracing.span_repository import SpanRepository

    repo = SpanRepository(tmp_db)
    span = TraceSpan(
        span_id="sp-test",
        run_id="run-abc",
        turn_id="t1",
        step_id="s1",
        tool_name="my_tool",
        start_ts="2024-01-01T10:00:00Z",
        end_ts="2024-01-01T10:00:01Z",
        input_hash="aaa",
        output_hash="bbb",
        success=True,
    )
    await repo.save(span)

    spans = await repo.list(run_id="run-abc")
    assert len(spans) == 1
    assert spans[0].span_id == "sp-test"
    assert spans[0].tool_name == "my_tool"
    assert spans[0].success is True


@pytest.mark.asyncio
async def test_tracer_creates_span_when_span_repo_provided():
    from citnega.packages.runtime.events.tracer import Tracer
    from citnega.packages.storage.repositories.invocation_repo import InvocationRepository
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.models.sessions import SessionConfig
    from citnega.packages.tools.builtin._tool_base import ToolOutput
    from citnega.packages.protocol.callables.results import InvokeResult

    invocation_repo = MagicMock(spec=InvocationRepository)
    invocation_repo.save = AsyncMock()

    span_repo = MagicMock()
    span_repo.save = AsyncMock()

    tracer = Tracer(invocation_repo, span_repo=span_repo)

    callable_mock = MagicMock()
    callable_mock.name = "test_tool"
    from citnega.packages.protocol.callables.types import CallableType
    callable_mock.callable_type = CallableType.TOOL

    input_mock = MagicMock()
    input_mock.model_dump_json = MagicMock(return_value='{"task": "test"}')

    from citnega.packages.protocol.callables.types import CallableType as _CT
    output = ToolOutput(result="done")
    result = InvokeResult(
        callable_name="test_tool",
        callable_type=_CT.TOOL,
        output=output,
        duration_ms=50,
    )

    ctx = CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        depth=1,
        session_config=SessionConfig(
            session_id="s1", name="test", framework="stub", default_model_id="x"
        ),
    )

    # Run in a real event loop so create_task works
    tracer.record(callable_mock, input_mock, result, ctx)
    await asyncio.sleep(0.05)  # let background tasks complete

    span_repo.save.assert_called_once()
    saved_span = span_repo.save.call_args[0][0]
    assert saved_span.tool_name == "test_tool"
    assert saved_span.run_id == "r1"
    assert saved_span.success is True
