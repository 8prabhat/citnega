"""SalesAgent — deal reviews, proposal writing, pipeline analysis, account plans."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SalesInput(BaseModel):
    task: str = Field(description="Sales task — e.g. 'review deal', 'write proposal', 'analyze pipeline', 'create account plan'.")
    deal_data: str = Field(default="", description="Path to deal data file (CRM export, opportunity notes).")
    account_name: str = Field(default="", description="Account or company name for context.")
    output_file: str = Field(default="", description="Output file path for generated document.")


class SalesAgent(SpecialistBase):
    name = "sales_agent"
    description = (
        "Sales strategy specialist for deal reviews, proposal writing, "
        "pipeline analysis, and account planning. Uses MEDDIC/BANT frameworks. "
        "Proposals include exec summary, value prop, pricing, and next steps. "
        "Use for: win/loss reviews, RFP responses, quarterly forecast summaries, "
        "strategic account plans."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = SalesInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior sales strategist with enterprise software experience. "
        "Deal reviews use MEDDIC (Metrics, Economic Buyer, Decision Criteria, Decision Process, "
        "Identify Pain, Champion) or BANT (Budget, Authority, Need, Timeline). "
        "Proposals always include: executive summary, problem statement, proposed solution, "
        "value proposition with ROI estimates, pricing, terms, and explicit next steps. "
        "Pipeline analyses segment by stage, flag at-risk deals (no activity > 14 days), "
        "and calculate weighted forecast. "
        "Account plans cover: account overview, stakeholder map, current state, strategic goals, "
        "growth opportunities, action plan with owners and dates."
    )
    TOOL_WHITELIST = [
        "write_docx", "create_excel", "read_kb", "write_kb", "email_composer",
    ]

    async def _execute(self, input: SalesInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.account_name:
            gathered.append(f"Account: {input.account_name}")

        if input.deal_data:
            read_tool = self._get_tool("read_file")
            if read_tool:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await read_tool.invoke(ReadFileInput(path=input.deal_data), child_ctx)
                    if result.success:
                        gathered.append(f"Deal data:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)

        if input.output_file and response:
            write_tool = self._get_tool("write_docx")
            if write_tool:
                try:
                    from citnega.packages.tools.builtin.write_docx import WriteDocxInput
                    await write_tool.invoke(WriteDocxInput(content=response, output_path=input.output_file), child_ctx)
                    tool_calls_made.append("write_docx")
                except Exception:
                    pass

        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
