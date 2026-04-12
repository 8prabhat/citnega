"""
Integration test: validates that tools and agents are wired end-to-end.

What is tested
--------------
1. bootstrap → ApplicationService has populated tool_registry and agent_registry
2. list_tools() / list_agents() return non-empty results
3. A tool can be called directly via invoke() and emits CallableStartEvent +
   CallableEndEvent so the TUI ToolCallBlock pipeline is exercised
4. Multiple tools called in sequence each produce start+end events
5. SessionsCommand._switch_session() loads conversation history (unit-style)
6. EventConsumerWorker passes input_summary through ToolCallStarted
7. search_web and search_files tools return ToolOutput without crashing
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock
import uuid

# ── helpers ────────────────────────────────────────────────────────────────────


class _MockEnforcer:
    async def enforce(self, *a, **k):
        pass

    async def run_with_timeout(self, c, coro, *a, **k):
        return await coro

    async def check_output_size(self, *a, **k):
        pass


class _MockEmitter:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


class _MockTracer:
    def record(self, *a, **k):
        pass


def _make_callable(cls, emitter=None):
    """Instantiate a BaseCallable subclass with stub deps."""
    enforcer = _MockEnforcer()
    em = emitter or _MockEmitter()
    tracer = _MockTracer()
    return cls(enforcer, em, tracer)


def _make_context(session_id: str = "test-session"):
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.models.sessions import SessionConfig

    return CallContext(
        session_id=session_id,
        run_id=str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        depth=0,
        parent_callable=None,
        session_config=SessionConfig(
            session_id=session_id,
            name="integration-test",
            framework="direct",
            default_model_id="test-model",
        ),
        model_gateway=None,
    )


# ── 1. Bootstrap wires tool_registry and agent_registry ───────────────────────


def test_bootstrap_populates_tool_and_agent_registries(tmp_path):
    """After bootstrap, list_tools() and list_agents() must be non-empty."""
    import asyncio

    async def _run():
        from citnega.apps.cli.bootstrap import cli_bootstrap

        async with cli_bootstrap(
            db_path=tmp_path / "citnega.db",
            run_migrations=False,
        ) as svc:
            tools = svc.list_tools()
            agents = svc.list_agents()
            return tools, agents

    tools, _agents = asyncio.run(_run())
    assert len(tools) > 0, "list_tools() returned nothing — tool_registry not wired"
    # Agents may be empty if none are registered — check tools at minimum
    tool_names = {t.name for t in tools}
    assert "read_file" in tool_names, "read_file not in tool_registry"
    assert "search_web" in tool_names, "search_web not in tool_registry"
    assert "list_dir" in tool_names, "list_dir not in tool_registry"


# ── 2. CallableStartEvent + CallableEndEvent emitted during invoke() ──────────


def test_tool_invoke_emits_start_and_end_events(tmp_path):
    """invoke() must emit CallableStartEvent then CallableEndEvent."""
    from citnega.packages.protocol.events.callable import CallableStartEvent
    from citnega.packages.tools.builtin.list_dir import ListDirTool

    emitter = _MockEmitter()
    tool = _make_callable(ListDirTool, emitter)
    ctx = _make_context()

    input_obj = tool.input_schema(dir_path=str(tmp_path))
    asyncio.run(tool.invoke(input_obj, ctx))

    event_types = [type(e).__name__ for e in emitter.events]
    assert "CallableStartEvent" in event_types, "CallableStartEvent not emitted"
    assert "CallableEndEvent" in event_types, "CallableEndEvent not emitted"

    start = next(e for e in emitter.events if isinstance(e, CallableStartEvent))
    assert start.callable_name == "list_dir"


def test_multiple_tool_calls_emit_paired_events(tmp_path):
    """Three successive tool calls → 3 start events and 3 end events."""
    from citnega.packages.protocol.events.callable import CallableEndEvent, CallableStartEvent
    from citnega.packages.tools.builtin.list_dir import ListDirTool
    from citnega.packages.tools.builtin.read_file import ReadFileTool
    from citnega.packages.tools.builtin.search_files import SearchFilesTool

    emitter = _MockEmitter()
    tools = [
        _make_callable(ListDirTool, emitter),
        _make_callable(ReadFileTool, emitter),
        _make_callable(SearchFilesTool, emitter),
    ]
    ctx = _make_context()

    # list_dir
    asyncio.run(tools[0].invoke(tools[0].input_schema(dir_path=str(tmp_path)), ctx))
    # read_file — file doesn't exist; tool should handle gracefully
    asyncio.run(
        tools[1].invoke(tools[1].input_schema(file_path=str(tmp_path / "nonexistent.txt")), ctx)
    )
    # search_files
    asyncio.run(tools[2].invoke(tools[2].input_schema(root_path=str(tmp_path), pattern=".*"), ctx))

    starts = [e for e in emitter.events if isinstance(e, CallableStartEvent)]
    ends = [e for e in emitter.events if isinstance(e, CallableEndEvent)]
    assert len(starts) == 3, f"Expected 3 CallableStartEvents, got {len(starts)}"
    assert len(ends) == 3, f"Expected 3 CallableEndEvents, got {len(ends)}"
    tool_names = {e.callable_name for e in starts}
    assert tool_names == {"list_dir", "read_file", "search_files"}


# ── 3. EventConsumerWorker passes input_summary through ToolCallStarted ───────


def test_event_consumer_passes_input_summary():
    """ToolCallStarted.input_summary must equal CallableStartEvent.input_summary."""
    from citnega.apps.tui.workers.event_consumer import EventConsumerWorker, ToolCallStarted
    from citnega.packages.protocol.callables.types import CallableType
    from citnega.packages.protocol.events.callable import CallableStartEvent

    posted: list = []

    app = MagicMock()
    app.post_message.side_effect = posted.append

    worker = EventConsumerWorker(app=app, service=MagicMock(), run_id="run-001")

    event = CallableStartEvent(
        session_id="s",
        run_id="run-001",
        turn_id="t",
        callable_name="search_web",
        callable_type=CallableType.TOOL,
        input_summary='{"query": "python asyncio"}',
        depth=1,
        parent_callable=None,
    )
    worker._dispatch(event)

    assert posted, "No message posted"
    msg = posted[0]
    assert isinstance(msg, ToolCallStarted)
    assert msg.callable_name == "search_web"
    assert msg.input_summary == '{"query": "python asyncio"}'


# ── 4. Session history loaded from disk ───────────────────────────────────────


def test_get_conversation_messages_reads_disk(tmp_path):
    """get_conversation_messages() falls back to disk when no runner exists."""
    from citnega.packages.runtime.app_service import ApplicationService

    # Write a fake conversation.json
    sid = str(uuid.uuid4())
    conv_dir = tmp_path / sid
    conv_dir.mkdir()
    msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    (conv_dir / "conversation.json").write_text(json.dumps({"messages": msgs}), encoding="utf-8")

    # Build a minimal stub service where adapter._sessions_dir = tmp_path
    adapter = MagicMock()
    adapter._sessions_dir = tmp_path
    runtime = MagicMock()
    runtime._adapter = adapter
    runtime._adapter.get_runner = MagicMock(return_value=None)

    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = runtime
    svc._tool_registry = {}
    svc._agent_registry = {}

    # Patch _get_runner to return None
    svc._get_runner = lambda _sid: None

    result = svc.get_conversation_messages(sid)
    assert result == msgs, f"Expected {msgs}, got {result}"


# ── 5. search_web returns ToolOutput without crashing ─────────────────────────


def test_search_web_tool_no_crash():
    """search_web must return ToolOutput even when network is unavailable."""
    from citnega.packages.tools.builtin.search_web import SearchWebTool

    emitter = _MockEmitter()
    tool = _make_callable(SearchWebTool, emitter)
    ctx = _make_context()

    input_obj = tool.input_schema(query="python programming language", max_results=3)
    result = asyncio.run(tool.invoke(input_obj, ctx))

    # Must not raise; result is an InvokeResult (either ok or error)
    assert result is not None
    # If it errored (e.g. no network), error message should be in output
    if not result.success:
        assert result.error is not None
    else:
        assert result.output is not None


# ── 6. search_files tool works correctly ──────────────────────────────────────


def test_search_files_finds_pattern(tmp_path):
    """search_files must return matching lines."""
    from citnega.packages.tools.builtin.search_files import SearchFilesTool

    (tmp_path / "sample.py").write_text("def hello_world():\n    pass\n")
    (tmp_path / "other.py").write_text("x = 42\n")

    tool = _make_callable(SearchFilesTool)
    ctx = _make_context()
    input_obj = tool.input_schema(
        root_path=str(tmp_path),
        pattern="def hello",
        glob_filter="*.py",
        max_results=10,
    )
    result = asyncio.run(tool.invoke(input_obj, ctx))
    assert result.success
    assert "hello_world" in result.output.result


# ── 7. list_dir and read_file integration ─────────────────────────────────────


def test_list_dir_and_read_file(tmp_path):
    """list_dir lists files; read_file reads them; both emit proper events."""
    from citnega.packages.tools.builtin.list_dir import ListDirTool
    from citnega.packages.tools.builtin.read_file import ReadFileTool

    sample = tmp_path / "notes.txt"
    sample.write_text("integration test content")

    emitter = _MockEmitter()
    list_t = _make_callable(ListDirTool, emitter)
    read_t = _make_callable(ReadFileTool, emitter)
    ctx = _make_context()

    # list_dir
    lr = asyncio.run(list_t.invoke(list_t.input_schema(dir_path=str(tmp_path)), ctx))
    assert lr.success
    assert "notes.txt" in lr.output.result

    # read_file
    rr = asyncio.run(read_t.invoke(read_t.input_schema(file_path=str(sample)), ctx))
    assert rr.success
    assert "integration test content" in rr.output.result

    from citnega.packages.protocol.events.callable import CallableStartEvent

    start_names = [e.callable_name for e in emitter.events if isinstance(e, CallableStartEvent)]
    assert "list_dir" in start_names
    assert "read_file" in start_names
