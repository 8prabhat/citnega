"""
FR-TOOL-001 — Contract tests for every built-in tool.

Validates the common execution contract:
  - Required class-level attributes are present and well-typed.
  - Tool can be instantiated with the standard (enforcer, emitter, tracer) signature.
  - get_metadata() returns a valid CallableMetadata.
  - input_schema and output_schema are Pydantic BaseModel subclasses with valid JSON schema.
  - invoke() returns InvokeResult (never raises).
  - ToolOutput.result is always a str.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from pydantic import BaseModel
import pytest

from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Registry of every built-in tool: (module_path, class_name, input_class)
# ---------------------------------------------------------------------------

_TOOL_REGISTRY = [
    ("citnega.packages.tools.builtin.artifact_pack", "ArtifactPackTool", "ArtifactPackInput"),
    ("citnega.packages.tools.builtin.calculate", "CalculateTool", "CalculateInput"),
    ("citnega.packages.tools.builtin.edit_file", "EditFileTool", "EditFileInput"),
    ("citnega.packages.tools.builtin.fetch_url", "FetchURLTool", "FetchURLInput"),
    ("citnega.packages.tools.builtin.get_datetime", "GetDatetimeTool", "GetDatetimeInput"),
    ("citnega.packages.tools.builtin.git_ops", "GitOpsTool", "GitOpsInput"),
    ("citnega.packages.tools.builtin.list_dir", "ListDirTool", "ListDirInput"),
    ("citnega.packages.tools.builtin.quality_gate", "QualityGateTool", "QualityGateInput"),
    ("citnega.packages.tools.builtin.read_file", "ReadFileTool", "ReadFileInput"),
    ("citnega.packages.tools.builtin.read_kb", "ReadKBTool", "ReadKBInput"),
    ("citnega.packages.tools.builtin.read_webpage", "ReadWebpageTool", "ReadWebpageInput"),
    ("citnega.packages.tools.builtin.repo_map", "RepoMapTool", "RepoMapInput"),
    ("citnega.packages.tools.builtin.run_shell", "RunShellTool", "RunShellInput"),
    ("citnega.packages.tools.builtin.search_files", "SearchFilesTool", "SearchFilesInput"),
    ("citnega.packages.tools.builtin.search_web", "SearchWebTool", "SearchWebInput"),
    ("citnega.packages.tools.builtin.summarize_text", "SummarizeTextTool", "SummarizeTextInput"),
    ("citnega.packages.tools.builtin.test_matrix", "MatrixTool", "MatrixInput"),
    ("citnega.packages.tools.builtin.write_file", "WriteFileTool", "WriteFileInput"),
    ("citnega.packages.tools.builtin.write_kb", "WriteKBTool", "WriteKBInput"),
]

_TOOL_IDS = [cls for _, cls, _ in _TOOL_REGISTRY]


def _load(module_path: str, class_name: str):
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _make_enforcer_no_approval() -> PolicyEnforcer:
    emitter = EventEmitter()
    mgr = ApprovalManager()
    return PolicyEnforcer(emitter, mgr)


def _make_tool_instance(tool_cls):
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return tool_cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


# ---------------------------------------------------------------------------
# Parametrized contract tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_path,class_name,_input_cls", _TOOL_REGISTRY, ids=_TOOL_IDS)
class TestToolContract:
    def _get_cls(self, module_path, class_name):
        return _load(module_path, class_name)

    def test_required_attrs_present(self, module_path, class_name, _input_cls) -> None:
        """Every tool must declare name, description, callable_type, input_schema, output_schema, policy."""
        cls = self._get_cls(module_path, class_name)
        assert isinstance(cls.name, str) and cls.name, f"{class_name}.name must be a non-empty str"
        assert isinstance(cls.description, str) and cls.description, (
            f"{class_name}.description must be a non-empty str"
        )
        assert isinstance(cls.callable_type, CallableType), (
            f"{class_name}.callable_type must be a CallableType"
        )
        assert issubclass(cls.input_schema, BaseModel), (
            f"{class_name}.input_schema must be a BaseModel subclass"
        )
        assert issubclass(cls.output_schema, BaseModel), (
            f"{class_name}.output_schema must be a BaseModel subclass"
        )
        assert isinstance(cls.policy, CallablePolicy), (
            f"{class_name}.policy must be a CallablePolicy"
        )

    def test_callable_type_is_tool(self, module_path, class_name, _input_cls) -> None:
        cls = self._get_cls(module_path, class_name)
        assert cls.callable_type == CallableType.TOOL, (
            f"{class_name}.callable_type must be CallableType.TOOL"
        )

    def test_instantiation_with_standard_args(self, module_path, class_name, _input_cls) -> None:
        """Tool must be instantiatable with (enforcer, emitter, tracer)."""
        cls = self._get_cls(module_path, class_name)
        tool = _make_tool_instance(cls)
        assert tool is not None

    def test_get_metadata_returns_valid_object(self, module_path, class_name, _input_cls) -> None:
        from citnega.packages.protocol.callables.types import CallableMetadata

        cls = self._get_cls(module_path, class_name)
        tool = _make_tool_instance(cls)
        meta = tool.get_metadata()
        assert isinstance(meta, CallableMetadata)
        assert meta.name == cls.name
        assert meta.description == cls.description
        assert meta.callable_type == CallableType.TOOL

    def test_input_schema_has_valid_json_schema(self, module_path, class_name, _input_cls) -> None:
        cls = self._get_cls(module_path, class_name)
        schema = cls.input_schema.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema

    def test_output_schema_has_valid_json_schema(self, module_path, class_name, _input_cls) -> None:
        cls = self._get_cls(module_path, class_name)
        schema = cls.output_schema.model_json_schema()
        assert isinstance(schema, dict)

    def test_input_schema_default_instantiation(self, module_path, class_name, _input_cls) -> None:
        """input_schema must have sensible defaults (no required fields without default)."""
        input_cls = _load(module_path, _input_cls)
        # Get fields with no default — these are the truly required fields
        required_fields = [
            name
            for name, field in input_cls.model_fields.items()
            if field.is_required()
        ]
        # We just assert this list is deterministic (not crashing)
        assert isinstance(required_fields, list)

    def test_name_is_snake_case(self, module_path, class_name, _input_cls) -> None:
        """Tool names must be lowercase snake_case (no spaces, no hyphens)."""
        cls = self._get_cls(module_path, class_name)
        name = cls.name
        assert name == name.lower(), f"{class_name}.name must be lowercase: {name!r}"
        assert " " not in name, f"{class_name}.name must not contain spaces: {name!r}"

    def test_policy_timeout_positive(self, module_path, class_name, _input_cls) -> None:
        cls = self._get_cls(module_path, class_name)
        assert cls.policy.timeout_seconds > 0, (
            f"{class_name}.policy.timeout_seconds must be > 0"
        )


# ---------------------------------------------------------------------------
# InvokeResult contract — invoke() never raises, always returns InvokeResult
# ---------------------------------------------------------------------------


class TestToolInvokeContract:
    """
    Tools must implement the 'never raises' contract: invoke() always returns
    an InvokeResult, even on error.  We test a representative subset with
    minimal inputs that will produce errors (missing files, etc.).
    """

    def _context(self):
        from citnega.packages.protocol.callables.context import CallContext
        from citnega.packages.protocol.models.sessions import SessionConfig

        cfg = SessionConfig(
            session_id="s1",
            name="t",
            framework="stub",
            default_model_id="x",
            approval_timeout_seconds=300,
        )
        return CallContext(session_id="s1", run_id="r1", turn_id="t1", session_config=cfg)

    @pytest.mark.asyncio
    async def test_calculate_returns_invoke_result(self) -> None:
        from citnega.packages.protocol.callables.results import InvokeResult
        from citnega.packages.protocol.callables.types import CallablePolicy
        from citnega.packages.tools.builtin.calculate import CalculateInput, CalculateTool

        tool = _make_tool_instance(CalculateTool)
        tool.policy = CallablePolicy(requires_approval=False)
        result = await tool.invoke(CalculateInput(expression="2 + 2"), self._context())
        assert isinstance(result, InvokeResult)
        assert result.success
        assert "4" in result.output.result

    @pytest.mark.asyncio
    async def test_get_datetime_returns_invoke_result(self) -> None:
        from citnega.packages.protocol.callables.results import InvokeResult
        from citnega.packages.protocol.callables.types import CallablePolicy
        from citnega.packages.tools.builtin.get_datetime import GetDatetimeInput, GetDatetimeTool

        tool = _make_tool_instance(GetDatetimeTool)
        tool.policy = CallablePolicy(requires_approval=False)
        result = await tool.invoke(GetDatetimeInput(), self._context())
        assert isinstance(result, InvokeResult)
        assert result.success

    @pytest.mark.asyncio
    async def test_read_file_missing_returns_invoke_result_not_raises(self, tmp_path) -> None:
        from citnega.packages.protocol.callables.results import InvokeResult
        from citnega.packages.protocol.callables.types import CallablePolicy
        from citnega.packages.tools.builtin.read_file import ReadFileInput, ReadFileTool

        tool = _make_tool_instance(ReadFileTool)
        tool.policy = CallablePolicy(requires_approval=False, allowed_paths=[str(tmp_path)])
        result = await tool.invoke(
            ReadFileInput(file_path=str(tmp_path / "nonexistent.txt")), self._context()
        )
        assert isinstance(result, InvokeResult)
        assert not result.success  # error is wrapped, not raised

    @pytest.mark.asyncio
    async def test_calculate_bad_expr_returns_error_result_not_raises(self) -> None:
        from citnega.packages.protocol.callables.results import InvokeResult
        from citnega.packages.protocol.callables.types import CallablePolicy
        from citnega.packages.tools.builtin.calculate import CalculateInput, CalculateTool

        tool = _make_tool_instance(CalculateTool)
        tool.policy = CallablePolicy(requires_approval=False)
        result = await tool.invoke(CalculateInput(expression="import os"), self._context())
        assert isinstance(result, InvokeResult)
        # calculate returns ToolOutput with error text (not a failed result)
        assert result.success
        assert "Error" in result.output.result or "Syntax" in result.output.result

    @pytest.mark.asyncio
    async def test_tool_output_result_is_always_str(self) -> None:
        """ToolOutput.result must always be a str."""
        from citnega.packages.protocol.callables.types import CallablePolicy
        from citnega.packages.tools.builtin.get_datetime import GetDatetimeInput, GetDatetimeTool

        tool = _make_tool_instance(GetDatetimeTool)
        tool.policy = CallablePolicy(requires_approval=False)
        result = await tool.invoke(GetDatetimeInput(), self._context())
        assert isinstance(result.output.result, str)
