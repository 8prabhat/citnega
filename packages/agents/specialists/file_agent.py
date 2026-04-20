"""FileAgent — filesystem read/write/search specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class FileAgentInput(BaseModel):
    task: str = Field(description="File operation task description.")
    file_path: str = Field(default="", description="Primary file path (if applicable).")
    content: str = Field(default="", description="Content to write (if applicable).")
    operation: str = Field(
        default="auto",
        description="'read' | 'write' | 'list' | 'search' | 'auto'",
    )


class FileAgent(SpecialistBase):
    """FileAgent — DEPRECATED. Use code_agent for all new usage (strict superset)."""

    name = "file_agent"
    llm_direct_access = False  # suppressed from LLM function-calling schema
    description = "Handles filesystem operations: read, write, list, and search files."
    callable_type = CallableType.SPECIALIST
    input_schema = FileAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=60.0,
        requires_approval=False,
        allowed_paths=["${SESSION_ID}"],
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a filesystem specialist. You help read, write, list, and search files. "
        "Always confirm file paths before writing. Never write outside allowed paths."
    )
    TOOL_WHITELIST = ["read_file", "write_file", "edit_file", "list_dir", "search_files"]

    async def _execute(self, input: FileAgentInput, context: CallContext) -> SpecialistOutput:
        op = input.operation
        tool_calls_made: list[str] = []

        # Auto-detect operation from task description
        if op == "auto":
            task_lower = input.task.lower()
            if "write" in task_lower or "create" in task_lower or "save" in task_lower:
                op = "write"
            elif "search" in task_lower or "find" in task_lower or "grep" in task_lower:
                op = "search"
            elif "list" in task_lower or "dir" in task_lower:
                op = "list"
            else:
                op = "read"

        child_ctx = context.child(self.name, self.callable_type)
        result_text = ""

        if op == "read" and input.file_path:
            tool = self._get_tool("read_file")
            if tool:
                from citnega.packages.tools.builtin.read_file import ReadFileInput

                res = await tool.invoke(ReadFileInput(file_path=input.file_path), child_ctx)
                if res.success and res.output:
                    result_text = res.get_output_field("result")
                    tool_calls_made.append("read_file")

        elif op == "write" and input.file_path and input.content:
            tool = self._get_tool("write_file")
            if tool:
                from citnega.packages.tools.builtin.write_file import WriteFileInput

                res = await tool.invoke(
                    WriteFileInput(file_path=input.file_path, content=input.content),
                    child_ctx,
                )
                if res.success and res.output:
                    result_text = res.get_output_field("result")
                    tool_calls_made.append("write_file")

        elif op == "list" and input.file_path:
            tool = self._get_tool("list_dir")
            if tool:
                from citnega.packages.tools.builtin.list_dir import ListDirInput

                res = await tool.invoke(ListDirInput(dir_path=input.file_path), child_ctx)
                if res.success and res.output:
                    result_text = res.get_output_field("result")
                    tool_calls_made.append("list_dir")

        if not result_text:
            # Fall back to model
            result_text = await self._call_model(input.task, context)

        return SpecialistOutput(response=result_text, tool_calls_made=tool_calls_made)
