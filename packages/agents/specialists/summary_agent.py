"""SummaryAgent — text summarisation specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SummaryInput(BaseModel):
    text: str = Field(description="Text to summarise.")
    style: str = Field(default="concise", description="'concise' | 'bullet' | 'detailed'")
    max_words: int = Field(default=200)
    focus: str = Field(default="")


class SummaryAgent(SpecialistBase):
    name = "summary_agent"
    description = "Summarises text using the summarize_text tool or direct model call."
    callable_type = CallableType.SPECIALIST
    input_schema = SummaryInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=True,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a summarisation specialist. Produce clear, accurate summaries "
        "that preserve key information. Match the requested style exactly."
    )
    TOOL_WHITELIST = ["summarize_text"]

    async def _execute(self, input: SummaryInput, context: CallContext) -> SpecialistOutput:
        tool = self._get_tool("summarize_text")
        if tool:
            from citnega.packages.tools.builtin.summarize_text import SummarizeTextInput

            child_ctx = context.child(self.name, self.callable_type)
            result = await tool.invoke(
                SummarizeTextInput(
                    text=input.text,
                    style=input.style,
                    max_words=input.max_words,
                    focus=input.focus,
                ),
                child_ctx,
            )
            if result.success and result.output:
                return SpecialistOutput(
                    response=result.get_output_field("result"),
                    tool_calls_made=["summarize_text"],
                )

        # Fallback: direct model call
        prompt = (
            f"Summarise the following text in {input.style} style "
            f"(max {input.max_words} words):\n\n{input.text}"
        )
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response)
