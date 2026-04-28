"""agent_delegate — peer agent-to-agent delegation without going through the orchestrator LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class AgentDelegateInput(BaseModel):
    agent_name: str = Field(description="Name of the specialist agent to delegate to.")
    task: str = Field(description="Task description to pass to the agent.")


class AgentDelegateTool(BaseCallable):
    name = "agent_delegate"
    description = (
        "Delegate a task to a named specialist agent via direct peer-to-peer call. "
        "Bypasses the orchestrator LLM for faster, lower-token agent chaining. "
        "Agent must be registered in context.sub_callables."
    )
    callable_type = CallableType.TOOL
    input_schema = AgentDelegateInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: AgentDelegateInput, context: CallContext) -> ToolOutput:
        sub_callables = getattr(context, "sub_callables", None) or {}
        agent = sub_callables.get(input.agent_name)
        if agent is None:
            available = ", ".join(sorted(sub_callables.keys())) if sub_callables else "none"
            return ToolOutput(
                result=f"[agent_delegate: '{input.agent_name}' not found. Available: {available}]"
            )

        try:
            child_ctx = context.child() if hasattr(context, "child") else context
            agent_input_cls = getattr(agent, "input_schema", None)
            if agent_input_cls is None:
                return ToolOutput(result=f"[agent_delegate: '{input.agent_name}' has no input_schema]")

            agent_input = agent_input_cls(task=input.task)
            output = await agent._execute(agent_input, child_ctx)

            result_text = getattr(output, "response", None) or getattr(output, "result", None)
            if result_text is None:
                result_text = output.model_dump_json()
            return ToolOutput(result=str(result_text)[:4096])

        except Exception as exc:
            return ToolOutput(result=f"[agent_delegate: '{input.agent_name}' raised {type(exc).__name__}: {exc}]")
