"""RouterAgent — classifies user intent and routes to the right specialist."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class RouterInput(BaseModel):
    user_input: str = Field(description="The user's request to be routed.")


class RouterOutput(BaseModel):
    agent: str = Field(description="Target agent id.")
    reason: str = Field(description="One-sentence routing reason.")


class RouterAgent(BaseAgent):
    agent_id = "router"
    name = "router_agent"
    description = "Classifies user intent and returns the best agent to handle it."
    callable_type = CallableType.CORE
    input_schema = RouterInput
    output_schema = RouterOutput

    SYSTEM_PROMPT = (
        "You are a routing agent. Analyse the user request and classify it. "
        'Reply ONLY with JSON: {"agent": "<id>", "reason": "<one sentence>"}.'
    )

    async def _execute(self, input: RouterInput, context: CallContext) -> RouterOutput:
        response = await self._call_model(input.user_input, context)
        try:
            data = json.loads(response.strip())
            return RouterOutput(
                agent=data.get("agent", "conversation"),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return RouterOutput(agent="conversation", reason="fallback: parse error")
