"""ReasoningAgent — explicit step-by-step chain-of-thought agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ReasoningInput(BaseModel):
    task: str = Field(description="The problem or question to reason about.")
    context: str = Field(default="", description="Optional background context.")


class ReasoningAgent(BaseAgent):
    agent_id = "reasoning"
    name = "reasoning_agent"
    description = "Solves problems step by step with explicit chain-of-thought."
    callable_type = CallableType.SPECIALIST
    input_schema = ReasoningInput
    output_schema = SpecialistOutput

    SYSTEM_PROMPT = (
        "Think step by step. Show every reasoning step. Conclude with a clear final answer."
    )

    async def _execute(self, input: ReasoningInput, context: CallContext) -> SpecialistOutput:
        user_msg = input.task
        if input.context:
            user_msg = f"Context:\n{input.context}\n\nTask:\n{input.task}"
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response)
