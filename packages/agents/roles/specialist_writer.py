"""SpecialistWriterAgent — domain-aware technical writer."""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType


class SpecialistWriterInput(BaseModel):
    task:    str = Field(description="Writing task description.")
    domain:  str = Field(default="general", description="Domain context: finance, legal, healthcare, etc.")
    content: str = Field(default="", description="Source material or draft to transform.")
    audience: str = Field(default="professional", description="Target audience.")


class SpecialistWriterAgent(BaseAgent):
    agent_id      = "specialist_writer"
    name          = "specialist_writer_agent"
    description   = "Domain-aware technical writer that produces polished, audience-appropriate documents."
    callable_type = CallableType.SPECIALIST
    input_schema  = SpecialistWriterInput
    output_schema = SpecialistOutput

    SYSTEM_PROMPT = (
        "You are a domain-aware technical writer. Transform information into polished documents. "
        "Adapt style to the domain and audience. Maintain factual accuracy."
    )

    async def _execute(self, input: SpecialistWriterInput, context: CallContext) -> SpecialistOutput:
        user_msg = (
            f"Domain: {input.domain}\n"
            f"Audience: {input.audience}\n"
            f"Task: {input.task}"
        )
        if input.content:
            user_msg += f"\n\nSource material:\n{input.content}"
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response)
