"""WritingAgent — long-form writing and editing specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class WritingAgentInput(BaseModel):
    task: str = Field(description="Writing task: draft, edit, rewrite, expand, translate.")
    content: str = Field(default="", description="Existing content to work with.")
    tone: str = Field(default="professional", description="Desired tone/style.")
    length: str = Field(default="medium", description="'short' | 'medium' | 'long'")
    language: str = Field(default="English")
    save_to: str = Field(default="", description="Optional file path to save output.")


_LENGTH_GUIDE = {
    "short": "100–200 words",
    "medium": "300–600 words",
    "long": "800–1500 words",
}


class WritingAgent(SpecialistBase):
    name = "writing_agent"
    description = "Drafts, edits, rewrites, expands, and translates text."
    callable_type = CallableType.SPECIALIST
    input_schema = WritingAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        allowed_paths=["${SESSION_ID}"],
        network_allowed=False,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a professional writing specialist. You draft, edit, rewrite, expand, "
        "and translate text. Match the requested tone and length precisely. "
        "Output only the final written content, no meta-commentary."
    )
    TOOL_WHITELIST = ["write_file", "read_file"]

    async def _execute(self, input: WritingAgentInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        length_guide = _LENGTH_GUIDE.get(input.length, "medium length")

        parts = [
            f"Task: {input.task}",
            f"Tone: {input.tone}",
            f"Target length: {length_guide}",
            f"Language: {input.language}",
        ]
        if input.content:
            parts.append(f"Existing content:\n{input.content}")

        system = self.SYSTEM_PROMPT
        response = await self._call_model("\n\n".join(parts), context, system_override=system)

        # Optionally save to file
        if input.save_to:
            write_tool = self._get_tool("write_file")
            if write_tool:
                from citnega.packages.tools.builtin.write_file import WriteFileInput

                child_ctx = context.child(self.name, self.callable_type)
                res = await write_tool.invoke(
                    WriteFileInput(file_path=input.save_to, content=response),
                    child_ctx,
                )
                if res.success:
                    tool_calls_made.append("write_file")

        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
