"""DataAgent — data analysis, shell execution, and structured output specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DataAgentInput(BaseModel):
    task: str = Field(description="Data analysis or processing task.")
    data: str = Field(default="", description="Inline data (CSV, JSON, text table, etc.)")
    script: str = Field(default="", description="Optional script to run.")
    output_format: str = Field(default="text", description="'text' | 'json' | 'csv' | 'markdown'")


class DataAgent(SpecialistBase):
    name = "data_agent"
    description = "Analyses data, runs scripts, and produces structured output."
    callable_type = CallableType.SPECIALIST
    input_schema = DataAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a data analysis specialist. You analyse structured and unstructured data, "
        "run scripts, and produce clear results in the requested format. "
        "Always explain your analysis steps."
    )
    TOOL_WHITELIST = ["run_shell", "read_file", "write_file"]

    async def _execute(self, input: DataAgentInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)

        script_output = ""
        if input.script:
            shell_tool = self._get_tool("run_shell")
            if shell_tool:
                from citnega.packages.tools.builtin.run_shell import RunShellInput

                res = await shell_tool.invoke(
                    RunShellInput(command=input.script, timeout=60.0),
                    child_ctx,
                )
                if res.success and res.output:
                    out = res.output  # type: ignore[attr-defined]
                    script_output = f"stdout:\n{out.stdout}\nstderr:\n{out.stderr}"
                    tool_calls_made.append("run_shell")

        # Build analysis prompt
        parts = [f"Task: {input.task}"]
        if input.data:
            parts.append(f"Data:\n{input.data}")
        if script_output:
            parts.append(f"Script output:\n{script_output}")
        parts.append(f"Output format: {input.output_format}")

        response = await self._call_model("\n\n".join(parts), context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
