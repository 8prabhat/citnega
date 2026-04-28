"""CustomerSupportAgent — ticket triage, KB article writing, feedback synthesis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CustomerSupportInput(BaseModel):
    task: str = Field(description="Support task — e.g. 'triage this ticket', 'write KB article', 'synthesize feedback', 'draft customer response'.")
    ticket_text: str = Field(default="", description="Raw ticket or customer message text.")
    customer_context: str = Field(default="", description="Customer account context (tier, history, product).")


class CustomerSupportAgent(SpecialistBase):
    name = "customer_support_agent"
    description = (
        "Customer Support specialist for ticket triage, knowledge base authoring, "
        "and feedback synthesis. Triages by urgency × impact. KB articles follow "
        "problem → root cause → steps → verification format. "
        "Use for: P1/P2 incident responses, how-to guides, NPS/CSAT analysis, "
        "customer-facing communications."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = CustomerSupportInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior customer support specialist. "
        "Triage tickets by urgency (time-sensitive?) × impact (how many customers affected?). "
        "Assign severity: P1 (critical, revenue impact), P2 (major, workaround exists), "
        "P3 (minor, cosmetic), P4 (feature request). "
        "KB articles follow: Problem statement → Root cause explanation → "
        "Step-by-step resolution (numbered) → Verification step → Related articles. "
        "Customer responses: empathise first, acknowledge the issue, provide next steps, "
        "set expectations for resolution time. "
        "Feedback synthesis: cluster by theme, calculate % occurrence, "
        "prioritise by frequency × severity, recommend top 3 actions."
    )
    TOOL_WHITELIST = [
        "read_kb", "write_kb", "read_file", "write_file", "email_composer",
    ]

    async def _execute(self, input: CustomerSupportInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.ticket_text:
            gathered.append(f"Ticket:\n{input.ticket_text}")
        if input.customer_context:
            gathered.append(f"Customer context:\n{input.customer_context}")

        kb_tool = self._get_tool("read_kb")
        if kb_tool and input.ticket_text:
            try:
                from citnega.packages.tools.builtin.read_kb import ReadKBInput
                result = await kb_tool.invoke(ReadKBInput(query=input.ticket_text[:200]), child_ctx)
                if result.success:
                    gathered.append(f"Relevant KB articles:\n{result.get_output_field('result')}")
                    tool_calls_made.append("read_kb")
            except Exception:
                pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
