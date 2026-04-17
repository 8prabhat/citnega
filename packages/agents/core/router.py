"""RouterAgent — LLM-based intent classifier and specialist router."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class RouterInput(BaseModel):
    user_input: str = Field(description="The user's request to be routed.")
    previous_results: list[str] = Field(
        default_factory=list,
        description="Summaries of results from prior specialist calls in this turn.",
    )


class RouterOutput(BaseModel):
    agent: str = Field(description="Name of the specialist agent to call next.")
    reason: str = Field(description="One-sentence routing reason.")
    is_complete: bool = Field(
        default=False,
        description="True when the accumulated results are sufficient — no further routing needed.",
    )


_SYSTEM_PROMPT = """\
You are a routing agent. Given the user's request and any prior specialist results,
decide which specialist agent should handle the next step — or declare the task complete.

Available agents (name → description):
{agent_menu}

Reply ONLY with valid JSON (no markdown fences):
{{"agent": "<name>", "reason": "<one sentence>", "is_complete": false}}

Set is_complete to true and agent to "none" when the accumulated results fully answer the request.
If no specialist is appropriate, route to "conversation_agent" (direct response).
"""


class RouterAgent(BaseCoreAgent):
    name = "router_agent"
    description = "LLM-based intent classifier; routes user requests to the right specialist."
    callable_type = CallableType.CORE
    input_schema = RouterInput
    output_schema = RouterOutput
    policy = CallablePolicy(timeout_seconds=30.0, requires_approval=False)

    def _emit_decision(
        self,
        context: CallContext,
        target: str,
        rationale: str,
        is_complete: bool = False,
        confidence: float | None = None,
        fallback: bool = False,
    ) -> None:
        from citnega.packages.protocol.events.routing import RouterDecisionEvent

        self._event_emitter.emit(
            RouterDecisionEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                selected_target=target,
                confidence=confidence,
                rationale=rationale,
                is_complete=is_complete,
                fallback=fallback,
            )
        )

    async def _execute(self, input: RouterInput, context: CallContext) -> RouterOutput:
        if context.model_gateway is None:
            self._emit_decision(
                context,
                target="conversation_agent",
                rationale="fallback: no model gateway",
                fallback=True,
            )
            return RouterOutput(
                agent="conversation_agent",
                reason="fallback: no model gateway",
                is_complete=False,
            )

        # Build agent menu from wired sub_callables
        menu_lines = []
        for c in self.list_sub_callables():
            if c.name not in (self.name, "conversation_agent"):
                menu_lines.append(f"  {c.name} — {getattr(c, 'description', '')}")
        # Always include conversation_agent as direct-answer fallback
        menu_lines.append("  conversation_agent — direct conversational response")
        agent_menu = "\n".join(menu_lines) or "  conversation_agent — direct conversational response"

        system = _SYSTEM_PROMPT.format(agent_menu=agent_menu)

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        messages = [ModelMessage(role="system", content=system)]

        if input.previous_results:
            context_block = "\n\n".join(
                f"Result {i + 1}:\n{r}" for i, r in enumerate(input.previous_results)
            )
            messages.append(
                ModelMessage(
                    role="system",
                    content=f"Prior specialist results:\n{context_block}",
                )
            )

        messages.append(ModelMessage(role="user", content=input.user_input))

        response = await context.model_gateway.generate(
            ModelRequest(messages=messages, stream=False, temperature=0.0)
        )

        raw = response.content.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            data = json.loads(raw)
            agent = str(data.get("agent", "conversation_agent")).strip()
            reason = str(data.get("reason", ""))
            is_complete = bool(data.get("is_complete", False))

            # Validate agent name against known sub_callables + sentinel
            known = {c.name for c in self.list_sub_callables()} | {"conversation_agent", "none"}
            fallback = False
            if agent not in known:
                reason = f"unknown agent '{agent}' — falling back to direct"
                agent = "conversation_agent"
                fallback = True

            self._emit_decision(
                context,
                target=agent,
                rationale=reason,
                is_complete=is_complete,
                fallback=fallback,
            )
            return RouterOutput(agent=agent, reason=reason, is_complete=is_complete)

        except (json.JSONDecodeError, KeyError, TypeError):
            self._emit_decision(
                context,
                target="conversation_agent",
                rationale="fallback: router parse error",
                fallback=True,
            )
            return RouterOutput(
                agent="conversation_agent",
                reason="fallback: router parse error",
                is_complete=False,
            )
