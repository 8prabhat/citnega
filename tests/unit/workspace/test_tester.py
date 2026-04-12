"""Unit tests for workspace/tester.py — CallableTester"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from citnega.packages.workspace.loader import DynamicLoader
from citnega.packages.workspace.templates import FallbackTemplates, ScaffoldSpec
from citnega.packages.workspace.tester import CallableTester, CodeTestResult, _mock_value

if TYPE_CHECKING:
    from pathlib import Path

# ── Stubs ──────────────────────────────────────────────────────────────────────


class _MockEnforcer:
    async def enforce(self, *a, **k):
        pass

    async def run_with_timeout(self, c, coro, *a, **k):
        return await coro

    async def check_output_size(self, *a, **k):
        pass


class _MockEmitter:
    def emit(self, *a):
        pass


def _make_loader():
    return DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())


def _load_tool(class_name: str, name: str, tmp_path: Path):
    spec = ScaffoldSpec(
        kind="tool",
        class_name=class_name,
        name=name,
        description="test tool",
        parameters=[{"name": "text", "type": "str", "description": "input"}],
    )
    source = FallbackTemplates.render_tool(spec)
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    return _make_loader().load_directory(tmp_path)[name]


def _load_agent(class_name: str, name: str, tmp_path: Path):
    spec = ScaffoldSpec(
        kind="agent",
        class_name=class_name,
        name=name,
        description="test agent",
        system_prompt="You help.",
    )
    source = FallbackTemplates.render_agent(spec)
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    return _make_loader().load_directory(tmp_path)[name]


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestCallableTester:
    def test_tool_passes(self, tmp_path: Path) -> None:
        inst = _load_tool("ToolPass", "tool_pass", tmp_path)
        result = asyncio.run(CallableTester().test(inst))
        assert result.passed

    def test_tool_output_is_string(self, tmp_path: Path) -> None:
        inst = _load_tool("ToolOut", "tool_out", tmp_path)
        result = asyncio.run(CallableTester().test(inst))
        assert isinstance(result.output, str)

    def test_duration_set(self, tmp_path: Path) -> None:
        inst = _load_tool("ToolDur", "tool_dur", tmp_path)
        result = asyncio.run(CallableTester().test(inst))
        assert result.duration_ms >= 0

    def test_agent_passes_without_gateway(self, tmp_path: Path) -> None:
        inst = _load_agent("AgentNoGw", "agent_no_gw", tmp_path)
        result = asyncio.run(CallableTester().test(inst, model_gateway=None))
        # SpecialistBase._call_model returns a stub when no gateway
        assert result.passed

    def test_failing_callable_captured(self, tmp_path: Path) -> None:
        """A callable that always raises should return passed=False with error."""
        # Write a tool that raises
        source = """\
from pydantic import BaseModel, Field
from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

class BrokenInput(BaseModel):
    text: str = Field(default="")

class BrokenTool(BaseCallable):
    name          = "broken_tool"
    description   = "always fails"
    callable_type = CallableType.TOOL
    input_schema  = BrokenInput
    output_schema = ToolOutput
    policy        = tool_policy()

    async def _execute(self, input, context):
        raise RuntimeError("intentional test failure")
"""
        (tmp_path / "broken_tool.py").write_text(source)
        inst = _make_loader().load_directory(tmp_path)["broken_tool"]
        result = asyncio.run(CallableTester().test(inst))
        assert not result.passed
        assert "intentional test failure" in result.error

    def test_code_test_result_bool(self) -> None:
        assert bool(CodeTestResult(passed=True)) is True
        assert bool(CodeTestResult(passed=False)) is False


class TestMockValue:
    def test_str_field(self) -> None:
        from pydantic import BaseModel, Field

        class M(BaseModel):
            x: str = Field()

        fi = M.model_fields["x"]
        assert isinstance(_mock_value(str, fi), str)

    def test_int_field(self) -> None:
        from pydantic import BaseModel, Field

        class M(BaseModel):
            x: int = Field()

        fi = M.model_fields["x"]
        assert isinstance(_mock_value(int, fi), int)

    def test_default_returned(self) -> None:
        from pydantic import BaseModel, Field

        class M(BaseModel):
            x: str = Field(default="hello")

        fi = M.model_fields["x"]
        assert _mock_value(str, fi) == "hello"

    def test_list_field(self) -> None:

        from pydantic import BaseModel, Field

        class M(BaseModel):
            x: list[str] = Field()

        fi = M.model_fields["x"]
        result = _mock_value(fi.annotation, fi)
        assert isinstance(result, list)
