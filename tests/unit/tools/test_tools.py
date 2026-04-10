"""Unit tests for all built-in tools."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.shared.errors import ArtifactError, ApprovalDeniedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_config() -> SessionConfig:
    return SessionConfig(
        session_id="test-sess",
        name="test",
        framework="stub",
        default_model_id="x",
        approval_timeout_seconds=300,
    )


def _context(depth: int = 0) -> CallContext:
    return CallContext(
        session_id="test-sess",
        run_id="run-1",
        turn_id="turn-1",
        depth=depth,
        session_config=_session_config(),
    )


def _make_tool(cls, policy_override: CallablePolicy | None = None):
    """Instantiate a tool with a no-approval PolicyEnforcer."""
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    tool = cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)
    if policy_override:
        tool.policy = policy_override
    return tool


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------

class TestReadFileTool:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.read_file import ReadFileTool, ReadFileInput
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        tool = _make_tool(ReadFileTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(ReadFileInput(file_path=str(f)), _context())
        assert result.success
        assert "hello world" in result.output.result

    @pytest.mark.asyncio
    async def test_read_missing_file_fails(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.read_file import ReadFileTool, ReadFileInput
        tool = _make_tool(ReadFileTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(ReadFileInput(file_path=str(tmp_path / "nope.txt")), _context())
        assert not result.success


# ---------------------------------------------------------------------------
# WriteFileTool — approval flow
# ---------------------------------------------------------------------------

class TestWriteFileTool:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.write_file import WriteFileTool, WriteFileInput
        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        tracer = MagicMock(spec=Tracer)
        tracer.record = MagicMock()
        tool = WriteFileTool(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)
        # Override policy: no approval required for this test
        tool.policy = CallablePolicy(
            requires_approval=False,
            allowed_paths=[str(tmp_path)],
        )
        dest = tmp_path / "out.txt"
        result = await tool.invoke(
            WriteFileInput(file_path=str(dest), content="test content"),
            _context(),
        )
        assert result.success
        assert dest.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_write_requires_approval_by_default(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.write_file import WriteFileTool, WriteFileInput
        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        tracer = MagicMock(spec=Tracer)
        tracer.record = MagicMock()
        tool = WriteFileTool(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)
        tool.policy = CallablePolicy(
            requires_approval=True,
            allowed_paths=[str(tmp_path)],
            timeout_seconds=5,
        )
        # With no one to approve + short timeout → ApprovalTimeoutError
        from citnega.packages.shared.errors import ApprovalTimeoutError
        cfg = _session_config()
        cfg = cfg.model_copy(update={"approval_timeout_seconds": 0.05})
        ctx = CallContext(
            session_id="test-sess",
            run_id="run-1",
            turn_id="turn-1",
            session_config=cfg,
        )
        result = await tool.invoke(
            WriteFileInput(file_path=str(tmp_path / "blocked.txt"), content="x"),
            ctx,
        )
        assert not result.success


# ---------------------------------------------------------------------------
# ListDirTool
# ---------------------------------------------------------------------------

class TestListDirTool:
    @pytest.mark.asyncio
    async def test_lists_files(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.list_dir import ListDirTool, ListDirInput
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        tool = _make_tool(ListDirTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(ListDirInput(dir_path=str(tmp_path)), _context())
        assert result.success
        assert "a.txt" in result.output.result
        assert "b.txt" in result.output.result

    @pytest.mark.asyncio
    async def test_missing_dir_fails(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.list_dir import ListDirTool, ListDirInput
        tool = _make_tool(ListDirTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(ListDirInput(dir_path=str(tmp_path / "nope")), _context())
        assert not result.success


# ---------------------------------------------------------------------------
# SearchFilesTool
# ---------------------------------------------------------------------------

class TestSearchFilesTool:
    @pytest.mark.asyncio
    async def test_finds_pattern(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.search_files import SearchFilesTool, SearchFilesInput
        (tmp_path / "doc.txt").write_text("Hello World\nFoo bar\n")
        tool = _make_tool(SearchFilesTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(
            SearchFilesInput(root_path=str(tmp_path), pattern="Hello"),
            _context(),
        )
        assert result.success
        assert "Hello" in result.output.result

    @pytest.mark.asyncio
    async def test_no_match_returns_message(self, tmp_path: Path) -> None:
        from citnega.packages.tools.builtin.search_files import SearchFilesTool, SearchFilesInput
        (tmp_path / "doc.txt").write_text("nothing here")
        tool = _make_tool(SearchFilesTool, CallablePolicy(allowed_paths=[str(tmp_path)], requires_approval=False))
        result = await tool.invoke(
            SearchFilesInput(root_path=str(tmp_path), pattern="ZZZNOMATCH"),
            _context(),
        )
        assert result.success
        assert "No matches" in result.output.result


# ---------------------------------------------------------------------------
# FetchURLTool (mock HTTP)
# ---------------------------------------------------------------------------

class TestFetchURLTool:
    @pytest.mark.asyncio
    async def test_fetch_returns_content(self) -> None:
        from citnega.packages.tools.builtin.fetch_url import FetchURLTool, FetchURLInput
        tool = _make_tool(FetchURLTool, CallablePolicy(requires_approval=False, network_allowed=True))
        async with respx.mock:
            respx.get("https://example.com").mock(
                return_value=httpx.Response(200, text="<html>Hello</html>",
                                            headers={"content-type": "text/html"})
            )
            result = await tool.invoke(
                FetchURLInput(url="https://example.com", extract_text=True),
                _context(),
            )
        assert result.success
        assert "Hello" in result.output.result

    @pytest.mark.asyncio
    async def test_fetch_http_error_fails(self) -> None:
        from citnega.packages.tools.builtin.fetch_url import FetchURLTool, FetchURLInput
        tool = _make_tool(FetchURLTool, CallablePolicy(requires_approval=False, network_allowed=True))
        async with respx.mock:
            respx.get("https://badhost.example").mock(
                side_effect=httpx.ConnectError("refused")
            )
            result = await tool.invoke(
                FetchURLInput(url="https://badhost.example"),
                _context(),
            )
        assert not result.success


# ---------------------------------------------------------------------------
# SummarizeTextTool — no model gateway
# ---------------------------------------------------------------------------

class TestSummarizeTextTool:
    @pytest.mark.asyncio
    async def test_without_gateway_returns_truncation(self) -> None:
        from citnega.packages.tools.builtin.summarize_text import SummarizeTextTool, SummarizeTextInput
        tool = _make_tool(SummarizeTextTool, CallablePolicy(requires_approval=False, network_allowed=True))
        result = await tool.invoke(
            SummarizeTextInput(text="Word " * 500, max_words=10),
            _context(),  # no model_gateway
        )
        assert result.success
        assert "unavailable" in result.output.result


# ---------------------------------------------------------------------------
# RunShellTool — approval gated
# ---------------------------------------------------------------------------

class TestRunShellTool:
    @pytest.mark.asyncio
    async def test_shell_with_approval_disabled_runs(self) -> None:
        from citnega.packages.tools.builtin.run_shell import RunShellTool, RunShellInput
        tool = _make_tool(RunShellTool, CallablePolicy(requires_approval=False))
        result = await tool.invoke(
            RunShellInput(command="echo hello", timeout=5.0),
            _context(),
        )
        assert result.success
        assert "hello" in result.output.stdout.lower()

    @pytest.mark.asyncio
    async def test_shell_nonzero_exit_still_succeeds(self) -> None:
        from citnega.packages.tools.builtin.run_shell import RunShellTool, RunShellInput
        tool = _make_tool(RunShellTool, CallablePolicy(requires_approval=False))
        result = await tool.invoke(
            RunShellInput(command="exit 1", timeout=5.0),
            _context(),
        )
        assert result.success
        assert result.output.return_code == 1
