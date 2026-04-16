from __future__ import annotations

import json

from pydantic import BaseModel

from citnega.packages.adapters.direct.runner import DirectModelRunner
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType


class _ToolInput(BaseModel):
    path: str = ""


class _ToolOutput(BaseModel):
    response: str = "ok"


class _DummyTool(IInvocable):
    callable_type = CallableType.TOOL
    input_schema = _ToolInput
    output_schema = _ToolOutput
    policy = CallablePolicy()

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = name

    async def invoke(self, input: BaseModel, context) -> InvokeResult:  # pragma: no cover
        return InvokeResult.ok(
            name=self.name,
            callable_type=self.callable_type,
            output=_ToolOutput(),
            duration_ms=1,
        )

    def get_metadata(self) -> CallableMetadata:
        return CallableMetadata(
            name=self.name,
            description=self.description,
            callable_type=self.callable_type,
            input_schema_json=self.input_schema.model_json_schema(),
            output_schema_json=self.output_schema.model_json_schema(),
            policy=self.policy,
        )


def _runner(*tools: _DummyTool) -> DirectModelRunner:
    runner = object.__new__(DirectModelRunner)
    runner._tools = {tool.name: tool for tool in tools}
    runner._all_callables = dict(runner._tools)
    return runner


def test_can_fan_out_parallel_safe_tools_with_distinct_paths() -> None:
    runner = _runner(_DummyTool("search_files"), _DummyTool("read_file"))
    pending = [
        {"id": "1", "function": {"name": "search_files", "arguments": json.dumps({"path": "/tmp/a"})}},
        {"id": "2", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/b"})}},
    ]

    assert runner._can_fan_out_tool_calls(pending) is True


def test_cannot_fan_out_conflicting_workspace_paths() -> None:
    runner = _runner(_DummyTool("read_file"), _DummyTool("read_file"))
    pending = [
        {"id": "1", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/shared"})}},
        {"id": "2", "function": {"name": "read_file", "arguments": json.dumps({"path": "/tmp/shared"})}},
    ]

    assert runner._can_fan_out_tool_calls(pending) is False
