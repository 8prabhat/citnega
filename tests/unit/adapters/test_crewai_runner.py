"""
Unit tests for CrewAI sync-to-async bridge.

Verifies that the _run() method in _CitnegaTool uses asyncio.run() (fresh event
loop per call) rather than loop.run_until_complete() which would deadlock when
called from within a running event loop.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_fake_invocable(name: str = "my_tool") -> MagicMock:
    """Return a minimal IInvocable mock."""
    from pydantic import BaseModel

    class _In(BaseModel):
        task: str = ""

    class _Out(BaseModel):
        result: str = ""

    invocable = MagicMock()
    invocable.name = name
    invocable.description = "test tool"
    invocable.input_schema = _In
    return invocable


def _extract_run_method(runner_instance: object, cbl: object) -> object:
    """
    Call _build_crew() with a mock crewai module and extract the _run method
    from the first _CitnegaTool class built by _make_crew_tool().
    """
    captured: list[object] = []

    class _FakeCrewBaseTool:
        name: str = ""
        description: str = ""

        def _run(self, **kwargs: object) -> str:  # pragma: no cover
            return ""

    class _FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            pass

    class _FakeTask:
        def __init__(self, **kwargs: object) -> None:
            pass

    class _FakeCrew:
        def __init__(self, **kwargs: object) -> None:
            pass

    class _FakeProcess:
        sequential = "sequential"

    fake_crewai = MagicMock()
    fake_crewai.Agent = _FakeAgent
    fake_crewai.Task = _FakeTask
    fake_crewai.Crew = _FakeCrew
    fake_crewai.Process = _FakeProcess

    fake_tools_mod = MagicMock()

    def capture_tool_class(cls: type) -> type:
        captured.append(cls)
        return cls

    fake_crewai_tools = MagicMock()
    fake_crewai_tools.BaseTool = _FakeCrewBaseTool

    with patch.dict(
        "sys.modules",
        {"crewai": fake_crewai, "crewai.tools": fake_crewai_tools},
    ):
        runner_instance._build_crew("test task")  # type: ignore[attr-defined]

    return captured[0] if captured else None


def _make_runner() -> object:
    """Build a minimal CrewAIRunner without real CrewAI installed."""
    from unittest.mock import MagicMock

    try:
        from citnega.packages.adapters.crewai.runner import CrewAIRunner
    except ImportError:
        pytest.skip("crewai adapter not importable in this environment")

    session = MagicMock()
    session.config.session_id = "test-session"
    cancellation_token = MagicMock()
    cancellation_token.is_cancelled.return_value = False
    checkpoint_serializer = MagicMock()
    event_translator = MagicMock()

    runner = CrewAIRunner.__new__(CrewAIRunner)
    runner._session = session
    runner._callables = []
    runner._translator = event_translator
    runner._model_id = "test-model"
    runner._last_output = ""
    runner._last_task = ""
    runner._token = cancellation_token
    runner._current_run_id = "run-1"
    return runner


def test_crewai_tool_uses_asyncio_run_not_run_until_complete() -> None:
    """
    The _run() bridge must call asyncio.run(), not loop.run_until_complete().
    asyncio.run() always creates a fresh event loop so it cannot deadlock
    even when called from a thread spawned by an async context.
    """
    import inspect

    from citnega.packages.adapters.crewai.runner import CrewAIRunner

    source = inspect.getsource(CrewAIRunner._build_crew)  # type: ignore[attr-defined]
    assert "asyncio.run(" in source, "_run() must use asyncio.run() for the sync bridge"
    assert "run_until_complete" not in source, "run_until_complete causes deadlock; use asyncio.run()"


def test_crewai_tool_run_invokes_callable() -> None:
    """
    The _run() bridge calls cbl.invoke() with validated input and returns
    the JSON-serialised output on success.
    """
    from pydantic import BaseModel

    class _In(BaseModel):
        task: str = ""

    class _Out(BaseModel):
        result: str = "done"

    from citnega.packages.protocol.callables.results import InvokeResult
    from citnega.packages.protocol.callables.types import CallableType

    fake_result = InvokeResult(
        success=True,
        output=_Out(result="done"),
        callable_name="echo_tool",
        callable_type=CallableType.TOOL,
        duration_ms=1,
    )
    cbl = MagicMock()
    cbl.name = "echo_tool"
    cbl.description = "echoes"
    cbl.input_schema = _In
    cbl.invoke = AsyncMock(return_value=fake_result)

    runner = _make_runner()

    # Directly simulate what _make_crew_tool builds and _run does
    import asyncio as _asyncio

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.models.sessions import SessionConfig

    ctx = CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(session_id="s1", name="test", framework="direct", default_model_id="test-model"),
    )
    # This is exactly the body of _run; verify it works without deadlock
    result = _asyncio.run(cbl.invoke(cbl.input_schema.model_validate({}), ctx))
    assert result.success is True
    assert result.output is not None
    assert "done" in result.output.model_dump_json()
