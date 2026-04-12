"""
DomainAgent — shared base for all domain specialist agents.

Domain agents are intentionally thin: they contain no business logic.
All specialisation comes from their YAML config (system_prompt, tools, policy).
The _execute() template is the same for every domain — only the config differs.

Adding a new domain: create a subclass, set agent_id + name + description.
No other changes needed (OCP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DomainInput(BaseModel):
    task: str = Field(description="The domain task or question.")
    context: str = Field(default="", description="Optional background context.")


class DomainAgent(BaseAgent):
    """
    Base for all domain specialist agents.

    Subclasses only need to set:
      agent_id    — matches agents.yaml key
      name        — unique callable name
      description — short human-readable description
    """

    callable_type = CallableType.SPECIALIST
    input_schema = DomainInput
    output_schema = SpecialistOutput

    async def _execute(self, input: DomainInput, context: CallContext) -> SpecialistOutput:
        user_msg = input.task
        if input.context:
            user_msg = f"Context:\n{input.context}\n\nTask:\n{input.task}"
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response)
