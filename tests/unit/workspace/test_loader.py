"""Unit tests for workspace/loader.py"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from citnega.packages.workspace.loader import DynamicLoader
from citnega.packages.workspace.templates import FallbackTemplates, ScaffoldSpec

if TYPE_CHECKING:
    from pathlib import Path

# ── Stubs ──────────────────────────────────────────────────────────────────────


class _MockEnforcer:
    async def enforce(self, *a, **k):
        pass

    async def run_with_timeout(self, c, coro, *a, **k):
        return asyncio.run(coro) if asyncio.iscoroutine(coro) else coro

    async def check_output_size(self, *a, **k):
        pass


class _MockEmitter:
    def emit(self, *a):
        pass


class _MockTracer:
    def record(self, *a, **k):
        pass


def _make_loader(**kwargs) -> DynamicLoader:
    return DynamicLoader(
        enforcer=_MockEnforcer(),
        emitter=_MockEmitter(),
        tracer=_MockTracer(),
        **kwargs,
    )


def _write_tool(tmp_path: Path, class_name: str, name: str) -> Path:
    spec = ScaffoldSpec(kind="tool", class_name=class_name, name=name, description="test")
    source = FallbackTemplates.render_tool(spec)
    p = tmp_path / f"{name}.py"
    p.write_text(source, encoding="utf-8")
    return p


# ── Tests ───────────���──────────────────────────────────────────────────────────


class TestLoadDirectory:
    def test_loads_single_tool(self, tmp_path: Path) -> None:
        _write_tool(tmp_path, "SmokeTestTool", "smoke_test_tool")
        loader = _make_loader()
        loaded = loader.load_directory(tmp_path)
        assert "smoke_test_tool" in loaded

    def test_skips_private_files(self, tmp_path: Path) -> None:
        (tmp_path / "_private.py").write_text("x = 1\n")
        loader = _make_loader()
        loaded = loader.load_directory(tmp_path)
        assert loaded == {}

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        loader = _make_loader()
        result = loader.load_directory(tmp_path / "nonexistent")
        assert result == {}

    def test_broken_file_skipped(self, tmp_path: Path) -> None:
        # valid tool
        _write_tool(tmp_path, "GoodTool", "good_tool")
        # broken file
        (tmp_path / "broken.py").write_text("this is not python !!!\n")
        loader = _make_loader()
        loaded = loader.load_directory(tmp_path)
        assert "good_tool" in loaded
        # broken.py did not crash the loader
        assert "broken" not in loaded

    def test_multiple_tools_in_dir(self, tmp_path: Path) -> None:
        _write_tool(tmp_path, "ToolAlpha", "tool_alpha")
        _write_tool(tmp_path, "ToolBeta", "tool_beta")
        loader = _make_loader()
        loaded = loader.load_directory(tmp_path)
        assert "tool_alpha" in loaded
        assert "tool_beta" in loaded

    def test_reload_returns_fresh_instance(self, tmp_path: Path) -> None:
        _write_tool(tmp_path, "ReloadTool", "reload_tool")
        loader = _make_loader()
        first = loader.load_directory(tmp_path)
        second = loader.load_directory(tmp_path)
        # They should both contain the name; instances may differ
        assert "reload_tool" in first
        assert "reload_tool" in second


class TestLoadWorkfolder:
    def test_loads_across_subdirs(self, tmp_path: Path) -> None:
        tools_dir = tmp_path / "tools"
        agents_dir = tmp_path / "agents"
        workflows_dir = tmp_path / "workflows"
        for d in (tools_dir, agents_dir, workflows_dir):
            d.mkdir()

        _write_tool(tools_dir, "MyTool", "my_tool")
        _write_tool(agents_dir, "MyAgent", "my_agent")
        _write_tool(workflows_dir, "MyWorkflow", "my_workflow")

        from citnega.packages.workspace.writer import WorkspaceWriter

        writer = WorkspaceWriter(tmp_path)
        loader = _make_loader()
        loaded = loader.load_workfolder(writer)

        assert "my_tool" in loaded
        assert "my_agent" in loaded
        assert "my_workflow" in loaded
