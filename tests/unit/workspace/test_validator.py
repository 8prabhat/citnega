"""Unit tests for workspace/validator.py"""

from __future__ import annotations

from citnega.packages.workspace.validator import CodeValidator, ValidationResult

_VALID_TOOL_SOURCE = """\
from pydantic import BaseModel, Field
from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

class MyToolInput(BaseModel):
    query: str = Field(description="query")

class MyTool(BaseCallable):
    name          = "my_tool"
    description   = "A test tool"
    callable_type = CallableType.TOOL
    input_schema  = MyToolInput
    output_schema = ToolOutput
    policy        = tool_policy()

    async def _execute(self, input, context):
        return ToolOutput(result="ok")
"""


class TestCodeValidator:
    def test_valid_tool_passes(self) -> None:
        result = CodeValidator().validate(_VALID_TOOL_SOURCE, "MyTool", "tool")
        assert result.ok
        assert result.errors == []

    def test_syntax_error_fails(self) -> None:
        bad_source = "class Foo(:\n    pass"
        result = CodeValidator().validate(bad_source, "Foo", "tool")
        assert not result.ok
        assert any("SyntaxError" in e for e in result.errors)

    def test_missing_class_fails(self) -> None:
        source = "x = 1\n"
        result = CodeValidator().validate(source, "MyTool", "tool")
        assert not result.ok
        assert any("not found" in e.lower() for e in result.errors)

    def test_missing_required_attrs_fails(self) -> None:
        source = """\
class MyTool:
    name = "my_tool"
    # missing description, callable_type, input_schema, output_schema, policy

    async def _execute(self, input, context):
        pass
"""
        result = CodeValidator().validate(source, "MyTool", "tool")
        assert not result.ok
        assert any("missing" in e.lower() for e in result.errors)

    def test_missing_execute_fails(self) -> None:
        source = """\
from pydantic import BaseModel
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

class MyTool:
    name          = "my_tool"
    description   = "test"
    callable_type = CallableType.TOOL
    input_schema  = BaseModel
    output_schema = ToolOutput
    policy        = tool_policy()
"""
        result = CodeValidator().validate(source, "MyTool", "tool")
        assert not result.ok
        assert any("_execute" in e for e in result.errors)

    def test_annotated_assignment_counts_as_attr(self) -> None:
        source = """\
from pydantic import BaseModel
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

class MyTool:
    name: str          = "my_tool"
    description: str   = "test"
    callable_type      = CallableType.TOOL
    input_schema       = BaseModel
    output_schema      = ToolOutput
    policy             = tool_policy()

    async def _execute(self, input, context):
        pass
"""
        result = CodeValidator().validate(source, "MyTool", "tool")
        assert result.ok

    def test_validation_result_bool_true(self) -> None:
        r = ValidationResult(ok=True, errors=[])
        assert bool(r) is True

    def test_validation_result_bool_false(self) -> None:
        r = ValidationResult(ok=False, errors=["something wrong"])
        assert bool(r) is False
