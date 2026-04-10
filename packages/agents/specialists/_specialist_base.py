"""
SpecialistBase — shared infrastructure for all specialist agents.

Specialists:
  - Extend BaseCallable (callable_type = SPECIALIST)
  - Hold a tool whitelist (list of tool names they may invoke)
  - Have a SYSTEM_PROMPT class variable (pure string, no runtime logic)
  - Generate text via context.model_gateway
  - Produce a SpecialistOutput containing the text response

Construction follows the same pattern as tools (injected policy_enforcer,
event_emitter, tracer).  The tool registry is injected separately so the
specialist can invoke sub-tools during _execute().
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Type

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.callables.interfaces import IInvocable

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer


class SpecialistOutput(BaseModel):
    """Standard output for all specialist agents."""
    response:      str = Field(description="Specialist's text response.")
    tool_calls_made: list[str] = Field(default_factory=list, description="Tool names invoked.")
    sources:       list[str] = Field(default_factory=list)


class SpecialistBase(BaseCallable):
    """
    Base for all specialist agents.

    Subclasses define:
      SYSTEM_PROMPT : str           — static system prompt
      TOOL_WHITELIST: list[str]     — names of tools this specialist may call
    """

    callable_type: CallableType = CallableType.SPECIALIST
    output_schema: Type[BaseModel] = SpecialistOutput

    SYSTEM_PROMPT:  str       = ""
    TOOL_WHITELIST: list[str] = []

    def __init__(
        self,
        policy_enforcer: "IPolicyEnforcer",
        event_emitter:   "IEventEmitter",
        tracer:          "ITracer",
        tool_registry:   "dict[str, IInvocable] | None" = None,
    ) -> None:
        super().__init__(policy_enforcer, event_emitter, tracer)
        self._tools: dict[str, IInvocable] = tool_registry or {}

    def _get_tool(self, name: str) -> "IInvocable | None":
        """Return a whitelisted tool by name, or None."""
        if name not in self.TOOL_WHITELIST:
            return None
        return self._tools.get(name)

    async def _call_model(
        self,
        user_input: str,
        context: "CallContext",
        system_override: str | None = None,
    ) -> str:
        """Call the model gateway with the specialist's system prompt."""
        if context.model_gateway is None:
            return f"(model gateway unavailable — specialist {self.name})"

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest
        messages = [
            ModelMessage(role="system", content=system_override or self.SYSTEM_PROMPT),
            ModelMessage(role="user",   content=user_input),
        ]
        response = await context.model_gateway.generate(
            ModelRequest(messages=messages, stream=False, temperature=0.5)
        )
        return response.content
