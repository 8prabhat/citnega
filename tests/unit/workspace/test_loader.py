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
        from citnega.packages.workspace.writer import WorkspaceWriter

        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()
        tools_dir = writer.tools_dir
        agents_dir = writer.agents_dir
        workflows_dir = writer.workflows_dir

        _write_tool(tools_dir, "MyTool", "my_tool")
        _write_tool(agents_dir, "MyAgent", "my_agent")
        _write_tool(workflows_dir, "MyWorkflow", "my_workflow")

        loader = _make_loader()
        loaded = loader.load_workfolder(writer)

        assert "my_tool" in loaded
        assert "my_agent" in loaded
        assert "my_workflow" in loaded

    def test_custom_core_agent_receives_overridden_tool_registry(self, tmp_path: Path) -> None:
        from citnega.packages.workspace.writer import WorkspaceWriter

        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()

        tool_source = """
from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class SearchInput(BaseModel):
    query: str = Field(default="")


class WorkspaceSearchWeb(BaseCallable):
    name = "search_web"
    description = "workspace override"
    callable_type = CallableType.TOOL
    input_schema = SearchInput
    output_schema = ToolOutput
    policy = tool_policy()

    async def _execute(self, input, context):
        return ToolOutput(result="workspace")
"""
        agent_source = """
from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class PlannerInput(BaseModel):
    goal: str = Field(default="")


class PlannerOutput(BaseModel):
    tool_class: str


class PlannerAgent(BaseCoreAgent):
    name = "planner_agent"
    description = "workspace planner"
    callable_type = CallableType.CORE
    input_schema = PlannerInput
    output_schema = PlannerOutput
    policy = CallablePolicy()

    async def _execute(self, input, context):
        tool = self._tool_registry["search_web"]
        return PlannerOutput(tool_class=type(tool).__name__)
"""
        (writer.tools_dir / "search_web.py").write_text(tool_source, encoding="utf-8")
        (writer.agents_dir / "planner_agent.py").write_text(agent_source, encoding="utf-8")

        class BuiltInSearchWeb:
            name = "search_web"

        loader = _make_loader(tool_registry={"search_web": BuiltInSearchWeb()})
        loaded = loader.load_workspace(writer)

        planner = loaded.agents["planner_agent"]
        assert planner._tool_registry["search_web"].__class__.__name__ == "WorkspaceSearchWeb"
