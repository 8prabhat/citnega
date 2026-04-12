"""
ConversationAgent — primary core agent for interactive sessions.

Uses hybrid routing: dispatches to specialists based on task type,
or handles general conversation directly via the model gateway.

Routing logic (StaticPriorityPolicy order):
  - research / search / web → ResearchAgent
  - summarise / tldr         → SummaryAgent
  - file / read / write      → FileAgent
  - data / analyse / csv     → DataAgent
  - write / draft / edit     → WritingAgent
  - general                  → direct model call
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ConversationInput(BaseModel):
    user_input: str = Field(description="The user's message or request.")
    session_context: str = Field(default="", description="Optional assembled context string.")


class ConversationOutput(BaseModel):
    response: str = Field(description="Agent's text response.")
    routed_to: str | None = Field(default=None, description="Specialist routed to, if any.")
    tool_calls: list[str] = Field(default_factory=list)


# Keyword → specialist name mapping (ordered by specificity)
_ROUTING_KEYWORDS: list[tuple[list[str], str]] = [
    (["research", "search the web", "look up", "find online"], "research_agent"),
    (["summarise", "summarize", "tldr", "tl;dr", "brief summary"], "summary_agent"),
    (["read file", "write file", "create file", "list dir", "search files"], "file_agent"),
    (
        ["analyse data", "analyze data", "data analysis", "run script", "csv", "json data"],
        "data_agent",
    ),
    (["draft", "write an essay", "rewrite", "edit text", "translate"], "writing_agent"),
]


def _route(user_input: str) -> str | None:
    """Return specialist name based on keyword heuristics, or None for direct."""
    lower = user_input.lower()
    for keywords, specialist in _ROUTING_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return specialist
    return None


class ConversationAgent(BaseCoreAgent):
    name = "conversation_agent"
    description = "Primary conversational agent with hybrid specialist routing."
    callable_type = CallableType.CORE
    input_schema = ConversationInput
    output_schema = ConversationOutput
    policy = CallablePolicy(
        timeout_seconds=300.0,
        requires_approval=False,
        network_allowed=True,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are Citnega, a helpful, honest, and capable AI assistant. "
        "Answer questions directly and concisely. Ask for clarification when needed. "
        "Never make up facts. Cite sources when available."
    )

    async def _execute(self, input: ConversationInput, context: CallContext) -> ConversationOutput:
        # Try specialist routing
        specialist_name = _route(input.user_input)
        if specialist_name:
            specialist = next(
                (c for c in self.list_sub_callables() if c.name == specialist_name),
                None,
            )
            if specialist:
                child_ctx = context.child(self.name, self.callable_type)
                # Build appropriate input for the specialist
                spec_input = specialist.input_schema.model_validate(
                    {"task": input.user_input, "query": input.user_input, "text": input.user_input}
                )
                result = await specialist.invoke(spec_input, child_ctx)
                if result.success and result.output:
                    out = result.output  # type: ignore[attr-defined]
                    return ConversationOutput(
                        response=out.response,
                        routed_to=specialist_name,
                        tool_calls=getattr(out, "tool_calls_made", []),
                    )

        # Direct model response
        if context.model_gateway is None:
            return ConversationOutput(
                response="(model gateway unavailable)",
                routed_to=None,
            )

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        messages = [
            ModelMessage(role="system", content=self.SYSTEM_PROMPT),
        ]
        if input.session_context:
            messages.append(
                ModelMessage(
                    role="system",
                    content=f"Session context:\n{input.session_context}",
                )
            )
        messages.append(ModelMessage(role="user", content=input.user_input))

        response = await context.model_gateway.generate(
            ModelRequest(messages=messages, stream=False, temperature=0.7)
        )
        return ConversationOutput(response=response.content, routed_to=None)
