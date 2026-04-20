"""
Unit tests for the five new utility tools added in the comprehensive wiring plan.

Covers:
- LogAnalyzerTool: pattern matching, file-not-found handling
- MemoryInspectorTool: returns graceful message when KB not connected
- DependencyAuditorTool: reads requirements.txt, handles empty dir
- APITesterTool: basic instantiation and schema
- PerfProfilerTool: basic instantiation and schema
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig


def _deps():
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return enforcer, emitter, tracer


def _make_tool(cls):
    enforcer, emitter, tracer = _deps()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


def _context():
    ctx = CallContext(
        session_id="test",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="test", name="test", framework="stub", default_model_id="x"
        ),
    )
    return ctx


# ---------------------------------------------------------------------------
# LogAnalyzerTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_analyzer_matches_error_pattern(tmp_path: Path) -> None:
    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput, LogAnalyzerTool

    log_file = tmp_path / "app.log"
    log_file.write_text(
        "INFO 2026-04-19 startup\n"
        "ERROR 2026-04-19 something went wrong\n"
        "WARN 2026-04-19 slow response\n"
        "INFO 2026-04-19 request done\n",
        encoding="utf-8",
    )

    tool = _make_tool(LogAnalyzerTool)
    inp = LogAnalyzerInput(file_path=str(log_file), pattern=r"ERROR|WARN")
    result = await tool._execute(inp, _context())

    assert "2 match" in result.result or "match" in result.result.lower()
    assert "ERROR" in result.result or "error" in result.result.lower()


@pytest.mark.asyncio
async def test_log_analyzer_file_not_found() -> None:
    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput, LogAnalyzerTool

    tool = _make_tool(LogAnalyzerTool)
    inp = LogAnalyzerInput(file_path="/nonexistent/does_not_exist.log")
    result = await tool._execute(inp, _context())

    assert "not found" in result.result.lower()


@pytest.mark.asyncio
async def test_log_analyzer_no_matches(tmp_path: Path) -> None:
    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput, LogAnalyzerTool

    log_file = tmp_path / "clean.log"
    log_file.write_text("INFO all good\nINFO everything fine\n", encoding="utf-8")

    tool = _make_tool(LogAnalyzerTool)
    inp = LogAnalyzerInput(file_path=str(log_file), pattern=r"ERROR|CRITICAL")
    result = await tool._execute(inp, _context())

    lower = result.result.lower()
    assert "no lines" in lower or "0 match" in lower or "no lines" in lower


@pytest.mark.asyncio
async def test_log_analyzer_invalid_pattern(tmp_path: Path) -> None:
    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput, LogAnalyzerTool

    log_file = tmp_path / "app.log"
    log_file.write_text("ERROR test\n", encoding="utf-8")

    tool = _make_tool(LogAnalyzerTool)
    inp = LogAnalyzerInput(file_path=str(log_file), pattern="[invalid regex (")
    result = await tool._execute(inp, _context())

    assert "invalid pattern" in result.result.lower()


# ---------------------------------------------------------------------------
# MemoryInspectorTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_inspector_returns_not_connected_without_kb() -> None:
    from citnega.packages.tools.builtin.memory_inspector import MemoryInspectorInput, MemoryInspectorTool

    tool = _make_tool(MemoryInspectorTool)
    inp = MemoryInspectorInput(action="list")
    ctx = _context()  # no knowledge_store attached

    result = await tool._execute(inp, ctx)
    lower = result.result.lower()
    assert "not connected" in lower or "no entries" in lower


@pytest.mark.asyncio
async def test_memory_inspector_list_with_empty_kb() -> None:
    from citnega.packages.tools.builtin.memory_inspector import MemoryInspectorInput, MemoryInspectorTool

    tool = _make_tool(MemoryInspectorTool)
    inp = MemoryInspectorInput(action="list")
    ctx = _context()

    kb_mock = MagicMock()
    kb_mock.list_all.return_value = []
    ctx = ctx.model_copy(update={"knowledge_store": kb_mock})

    result = await tool._execute(inp, ctx)
    assert "empty" in result.result.lower() or "0" in result.result


@pytest.mark.asyncio
async def test_memory_inspector_stats_counts_entries() -> None:
    from citnega.packages.tools.builtin.memory_inspector import MemoryInspectorInput, MemoryInspectorTool

    tool = _make_tool(MemoryInspectorTool)
    inp = MemoryInspectorInput(action="stats")
    ctx = _context()

    entry = MagicMock()
    entry.title = "Research: AI trends"
    kb_mock = MagicMock()
    kb_mock.list_all.return_value = [entry, entry]
    ctx = ctx.model_copy(update={"knowledge_store": kb_mock})

    result = await tool._execute(inp, ctx)
    assert "2" in result.result


# ---------------------------------------------------------------------------
# DependencyAuditorTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dependency_auditor_reads_requirements_txt(tmp_path: Path) -> None:
    from citnega.packages.tools.builtin.dependency_auditor import DependencyAuditorInput, DependencyAuditorTool

    (tmp_path / "requirements.txt").write_text(
        "requests==2.28.0\nhttpx==0.24.0\npydantic>=2.0\n",
        encoding="utf-8",
    )

    tool = _make_tool(DependencyAuditorTool)
    inp = DependencyAuditorInput(path=str(tmp_path), check_latest=False)
    result = await tool._execute(inp, _context())

    lower = result.result.lower()
    assert "requests" in lower or "httpx" in lower or "pydantic" in lower


@pytest.mark.asyncio
async def test_dependency_auditor_empty_dir(tmp_path: Path) -> None:
    from citnega.packages.tools.builtin.dependency_auditor import DependencyAuditorInput, DependencyAuditorTool

    tool = _make_tool(DependencyAuditorTool)
    inp = DependencyAuditorInput(path=str(tmp_path), check_latest=False)
    result = await tool._execute(inp, _context())

    assert isinstance(result.result, str)
    assert len(result.result) > 0


@pytest.mark.asyncio
async def test_dependency_auditor_invalid_path() -> None:
    from citnega.packages.tools.builtin.dependency_auditor import DependencyAuditorInput, DependencyAuditorTool

    tool = _make_tool(DependencyAuditorTool)
    inp = DependencyAuditorInput(path="/nonexistent/dir/that/does/not/exist", check_latest=False)
    result = await tool._execute(inp, _context())

    assert isinstance(result.result, str)


# ---------------------------------------------------------------------------
# APITesterTool — schema and name
# ---------------------------------------------------------------------------


def test_api_tester_tool_name_and_type() -> None:
    from citnega.packages.tools.builtin.api_tester import APITesterTool

    tool = _make_tool(APITesterTool)
    assert tool.name == "api_tester"


def test_api_tester_input_schema_has_url_field() -> None:
    from citnega.packages.tools.builtin.api_tester import APITesterInput

    fields = APITesterInput.model_fields
    assert "url" in fields
    assert "method" in fields


# ---------------------------------------------------------------------------
# PerfProfilerTool — schema and name
# ---------------------------------------------------------------------------


def test_perf_profiler_tool_name() -> None:
    from citnega.packages.tools.builtin.perf_profiler import PerfProfilerTool

    tool = _make_tool(PerfProfilerTool)
    assert tool.name == "perf_profiler"


def test_perf_profiler_requires_approval() -> None:
    from citnega.packages.tools.builtin.perf_profiler import PerfProfilerTool

    tool = _make_tool(PerfProfilerTool)
    assert tool.policy.requires_approval is True


# ---------------------------------------------------------------------------
# ConfigBar helpers (widget utility functions)
# ---------------------------------------------------------------------------


def test_context_bar_config_line_returns_string() -> None:
    from citnega.apps.tui.widgets.context_bar import _build_config_line

    line = _build_config_line()
    assert isinstance(line, str) and len(line) > 0
    assert "rounds" in line
    assert "policy" in line


def test_context_bar_config_line_no_session_fields() -> None:
    """Config line must not duplicate state-line fields (folder, model, mode, tokens)."""
    from citnega.apps.tui.widgets.context_bar import _build_config_line

    line = _build_config_line()
    assert "folder" not in line.lower()
    assert "model" not in line.lower()
    assert "ctx:" not in line.lower()
    assert "token" not in line.lower()
