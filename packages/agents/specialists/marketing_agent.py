"""MarketingAgent — campaign briefs, content calendars, SEO audits, brand guidelines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class MarketingInput(BaseModel):
    task: str = Field(description="Marketing task — e.g. 'create campaign brief', 'build content calendar', 'audit SEO', 'write brand guidelines'.")
    brand_file: str = Field(default="", description="Path to existing brand guidelines or brand context file.")
    audience: str = Field(default="", description="Target audience description.")
    channel: str = Field(default="", description="Marketing channel (e.g. 'email', 'social', 'paid search', 'content').")


class MarketingAgent(SpecialistBase):
    name = "marketing_agent"
    description = (
        "Marketing strategy specialist for campaign briefs, content calendars, "
        "SEO audits, and brand guidelines. Follows structured brief formats with "
        "objective → audience → message → channel → KPIs → budget. "
        "Use for: go-to-market plans, editorial calendars, keyword strategies, "
        "tone-of-voice guides."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = MarketingInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior marketing strategist with B2B and B2C experience. "
        "Campaign briefs always follow: objective → target audience → key message → "
        "channel mix → KPIs → budget range → timeline. "
        "Content calendars include: date, channel, format, topic, CTA, owner, status. "
        "SEO audits cover: title tags, meta descriptions, heading hierarchy, keyword density, "
        "internal linking, page speed signals. "
        "Brand guidelines define: voice (adjectives), tone by context, vocabulary to use/avoid, "
        "visual identity notes. "
        "Every recommendation is specific and actionable — no generic advice."
    )
    TOOL_WHITELIST = [
        "search_web", "write_docx", "render_chart", "email_composer", "read_kb", "write_kb",
    ]

    async def _execute(self, input: MarketingInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.audience:
            gathered.append(f"Target audience: {input.audience}")
        if input.channel:
            gathered.append(f"Channel: {input.channel}")

        if input.brand_file:
            read_tool = self._get_tool("read_file")
            if read_tool:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await read_tool.invoke(ReadFileInput(path=input.brand_file), child_ctx)
                    if result.success:
                        gathered.append(f"Brand context:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
