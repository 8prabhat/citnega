"""summarize_text — summarise long text using the model gateway."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SummarizeTextInput(BaseModel):
    text: str = Field(description="Text to summarise.")
    style: str = Field(default="concise", description="'concise' | 'bullet' | 'detailed'")
    max_words: int = Field(default=200, description="Approximate max words in summary.")
    focus: str = Field(default="", description="Optional focus area for the summary.")


_STYLE_PROMPTS = {
    "concise": "Write a concise summary in {max_words} words or fewer.",
    "bullet": "Write a bullet-point summary (max {max_words} words total).",
    "detailed": "Write a detailed summary covering all key points (max {max_words} words).",
}


class SummarizeTextTool(BaseCallable):
    name = "summarize_text"
    description = "Summarise a block of text using the model gateway."
    callable_type = CallableType.TOOL
    input_schema = SummarizeTextInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=True,  # reaches model gateway (may be remote)
    )

    async def _execute(self, input: SummarizeTextInput, context: CallContext) -> ToolOutput:
        if context.model_gateway is None:
            # Fallback: simple truncation with note
            words = input.text.split()[: input.max_words]
            return ToolOutput(result=" ".join(words) + "…  (model gateway unavailable)")

        style_tmpl = _STYLE_PROMPTS.get(input.style, _STYLE_PROMPTS["concise"])
        style_instr = style_tmpl.format(max_words=input.max_words)
        focus_instr = f" Focus on: {input.focus}." if input.focus else ""

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        request = ModelRequest(
            messages=[
                ModelMessage(
                    role="system",
                    content=f"{style_instr}{focus_instr}",
                ),
                ModelMessage(role="user", content=input.text),
            ],
            stream=False,
            temperature=0.3,
        )
        try:
            response = await context.model_gateway.generate(request)
            return ToolOutput(result=response.content)
        except Exception as exc:
            raise CallableError(f"Summarization failed: {exc}") from exc
