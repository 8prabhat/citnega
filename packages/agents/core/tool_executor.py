"""ToolExecutorAgent — orchestrates explicit tool execution requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ToolExecutorInput(BaseModel):
    task: str = Field(description="What to accomplish via tool execution.")
    tool_hint: str = Field(default="", description="Suggested tool name if known.")


class ToolExecutorAgent(BaseAgent):
    agent_id = "tool_executor"
    name = "tool_executor_agent"
    description = "Executes tool operations precisely and returns structured results."
    callable_type = CallableType.SPECIALIST
    input_schema = ToolExecutorInput
    output_schema = SpecialistOutput

    SYSTEM_PROMPT = (
        "You are a tool execution agent. Execute the requested operations precisely. "
        "If a tool fails, explain why and suggest alternatives."
    )

    TOOL_WHITELIST = ["read_file", "list_dir", "search_files", "run_shell", "fetch_url"]

    async def _execute(self, input: ToolExecutorInput, context: CallContext) -> SpecialistOutput:
        # List available tools for the model to choose
        available = ", ".join(self.TOOL_WHITELIST)
        user_msg = f"Available tools: {available}\n\nTask: {input.task}"
        if input.tool_hint:
            user_msg += f"\nSuggested tool: {input.tool_hint}"
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response)
