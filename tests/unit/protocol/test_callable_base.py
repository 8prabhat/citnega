"""
Unit tests for BaseCallable Template Method.

Tests verify the execution skeleton:
  validate → policy → emit start → _execute → emit end → trace → return InvokeResult
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.results import InvokeResult, StreamChunk, StreamChunkKind
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.shared.errors import CitnegaError, CallablePolicyError


# ── Helpers ────────────────────────────────────────────────────────────────────

class _Input(BaseModel):
    value: str


class _Output(BaseModel):
    result: str


class _SuccessCallable(BaseCallable):
    name          = "success_tool"
    description   = "Always succeeds"
    callable_type = CallableType.TOOL
    input_schema  = _Input
    output_schema = _Output
    policy        = CallablePolicy()

    async def _execute(self, input: BaseModel, context: CallContext) -> BaseModel:
        assert isinstance(input, _Input)
        return _Output(result=f"done:{input.value}")


class _CitnegaErrorCallable(BaseCallable):
    name          = "citnega_error_tool"
    description   = "Raises CitnegaError"
    callable_type = CallableType.TOOL
    input_schema  = _Input
    output_schema = _Output

    async def _execute(self, input: BaseModel, context: CallContext) -> BaseModel:
        raise CitnegaError("expected error")


class _UnhandledErrorCallable(BaseCallable):
    name          = "unhandled_error_tool"
    description   = "Raises unhandled exception"
    callable_type = CallableType.TOOL
    input_schema  = _Input
    output_schema = _Output

    async def _execute(self, input: BaseModel, context: CallContext) -> BaseModel:
        raise RuntimeError("unexpected crash")


def _make_context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="test",
            framework="adk",
            default_model_id="gemma3",
        ),
    )


def _make_deps() -> tuple[AsyncMock, MagicMock, MagicMock]:
    policy_enforcer = AsyncMock()
    policy_enforcer.enforce.return_value = None
    policy_enforcer.check_output_size.return_value = None
    # run_with_timeout must actually await the coroutine so _execute runs
    async def _run_with_timeout(callable_obj, coro, context, emitter):  # noqa: ANN001
        return await coro
    policy_enforcer.run_with_timeout.side_effect = _run_with_timeout
    event_emitter   = MagicMock()
    tracer          = MagicMock()
    return policy_enforcer, event_emitter, tracer


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestBaseCallableSuccess:
    @pytest.mark.asyncio
    async def test_returns_invoke_result_on_success(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        ctx  = _make_context()

        result = await tool.invoke(_Input(value="hello"), ctx)

        assert result.success is True
        assert isinstance(result.output, _Output)
        assert result.output.result == "done:hello"  # type: ignore[union-attr]
        assert result.callable_name == "success_tool"

    @pytest.mark.asyncio
    async def test_policy_enforcer_called(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        await tool.invoke(_Input(value="x"), _make_context())
        pe.enforce.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_events_emitted(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        await tool.invoke(_Input(value="x"), _make_context())
        assert ee.emit.call_count == 2  # start + end

    @pytest.mark.asyncio
    async def test_tracer_called(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        await tool.invoke(_Input(value="x"), _make_context())
        tr.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_duration_ms_is_positive(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        result = await tool.invoke(_Input(value="x"), _make_context())
        assert result.duration_ms >= 0


class TestBaseCallableCitnegaError:
    @pytest.mark.asyncio
    async def test_citnega_error_captured_in_result(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _CitnegaErrorCallable(pe, ee, tr)
        result = await tool.invoke(_Input(value="x"), _make_context())

        assert result.success is False
        assert result.error is not None
        assert result.error.message == "expected error"

    @pytest.mark.asyncio
    async def test_events_still_emitted_on_error(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _CitnegaErrorCallable(pe, ee, tr)
        await tool.invoke(_Input(value="x"), _make_context())
        assert ee.emit.call_count == 2


class TestBaseCallableUnhandledError:
    @pytest.mark.asyncio
    async def test_unhandled_exception_wrapped(self) -> None:
        from citnega.packages.shared.errors import UnhandledCallableError

        pe, ee, tr = _make_deps()
        tool = _UnhandledErrorCallable(pe, ee, tr)
        result = await tool.invoke(_Input(value="x"), _make_context())

        assert result.success is False
        assert isinstance(result.error, UnhandledCallableError)
        assert result.error.error_code == "CALLABLE_UNHANDLED"


class TestBaseCallablePolicyDenial:
    @pytest.mark.asyncio
    async def test_policy_error_captured_in_result(self) -> None:
        pe, ee, tr = _make_deps()
        pe.enforce.side_effect = CallablePolicyError("depth exceeded")

        tool = _SuccessCallable(pe, ee, tr)
        result = await tool.invoke(_Input(value="x"), _make_context())

        assert result.success is False
        assert isinstance(result.error, CallablePolicyError)


class TestStreamInvoke:
    @pytest.mark.asyncio
    async def test_default_stream_yields_result_then_terminal(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)

        chunks = []
        async for chunk in tool.stream_invoke(_Input(value="x"), _make_context()):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].kind == StreamChunkKind.RESULT
        assert chunks[1].kind == StreamChunkKind.TERMINAL


class TestGetMetadata:
    def test_metadata_fields(self) -> None:
        pe, ee, tr = _make_deps()
        tool = _SuccessCallable(pe, ee, tr)
        meta = tool.get_metadata()
        assert meta.name == "success_tool"
        assert meta.callable_type == CallableType.TOOL
        assert "value" in str(meta.input_schema_json)
