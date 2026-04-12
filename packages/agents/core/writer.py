"""WriterAgent — content generation and editing specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class WriterInput(BaseModel):
    task: str = Field(description="Writing task: draft, edit, summarise, translate, etc.")
    content: str = Field(default="", description="Existing content to edit/refine (optional).")
    tone: str = Field(
        default="professional", description="Desired tone: professional/casual/technical/academic."
    )
    length: str = Field(default="medium", description="Target length: short/medium/long.")


class WriterAgent(BaseAgent):
    agent_id = "writer"
    name = "writer_agent"
    description = "Expert writer and editor for any content type and domain."
    callable_type = CallableType.SPECIALIST
    input_schema = WriterInput
    output_schema = SpecialistOutput

    SYSTEM_PROMPT = (
        "You are an expert writer and editor. Produce clear, well-structured, "
        "and engaging content. Match the requested tone and length."
    )

    async def _execute(self, input: WriterInput, context: CallContext) -> SpecialistOutput:
        user_msg = f"Task: {input.task}\nTone: {input.tone}\nLength: {input.length}"
        if input.content:
            user_msg += f"\n\nExisting content:\n{input.content}"
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response)
