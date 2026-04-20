"""BusinessAnalystAgent — requirements elicitation, gap analysis, stakeholder deliverables."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class BusinessAnalystInput(BaseModel):
    task: str = Field(description="Business analysis task — e.g. 'gather requirements for X', 'write user stories for Y', 'gap analysis between A and B'.")
    context: str = Field(default="", description="Background information, existing documents, or data to consider.")
    output_format: str = Field(default="markdown", description="Preferred output format: markdown | docx | pptx | excel")
    output_file: str = Field(default="", description="Optional file path to write the output document.")


class BusinessAnalystAgent(SpecialistBase):
    name = "business_analyst_agent"
    description = (
        "Business analysis specialist for requirements elicitation, user stories, gap analysis, "
        "process mapping, and stakeholder deliverables. Can produce BRDs, FRDs, user story maps, "
        "RACI matrices, and executive summaries. Writes output to Word, PDF, PowerPoint, or Excel."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = BusinessAnalystInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior business analyst. Produce clear, structured deliverables: "
        "requirements documents, user stories with acceptance criteria, gap analyses, "
        "process flows, and stakeholder reports. Use structured formats (tables, numbered lists). "
        "Always distinguish between current state (as-is) and future state (to-be). "
        "Flag ambiguities and assumptions explicitly."
    )
    TOOL_WHITELIST = [
        "read_file", "write_docx", "write_pdf", "create_ppt", "create_excel",
        "sql_query", "pandas_analyze", "web_scraper", "write_kb", "read_kb", "git_ops",
    ]

    async def _execute(self, input: BusinessAnalystInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)

        prior_context = await self._read_kb_context(input.task, child_ctx, tool_calls_made)

        sections = [f"Task: {input.task}"]
        if input.context:
            sections.append(f"Context provided:\n{input.context}")
        if prior_context:
            sections.append(f"Relevant prior knowledge:\n{prior_context}")
        sections.append(
            f"Preferred output format: {input.output_format}"
            + (f"\nOutput file: {input.output_file}" if input.output_file else "")
        )

        prompt = "\n\n---\n\n".join(sections)
        response = await self._call_model(prompt, context)

        # Write to file if requested and tool available
        if input.output_file:
            await self._write_output(input.output_format, input.output_file, input.task, response, child_ctx, tool_calls_made)

        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)

    async def _read_kb_context(self, query: str, ctx, tool_calls: list[str]) -> str:
        kb_tool = self._get_tool("read_kb")
        if not kb_tool:
            return ""
        try:
            from citnega.packages.tools.builtin.read_kb import ReadKBInput
            result = await kb_tool.invoke(ReadKBInput(query=query, max_results=3), ctx)
            if result.success:
                text = result.get_output_field("result") or ""
                if text and "not connected" not in text:
                    tool_calls.append("read_kb")
                    return text
        except Exception:
            pass
        return ""

    async def _write_output(self, fmt: str, path: str, title: str, content: str, ctx, tool_calls: list[str]) -> None:
        fmt = fmt.lower()
        try:
            if fmt == "docx":
                tool = self._get_tool("write_docx")
                if tool:
                    from citnega.packages.tools.builtin.write_docx import DocxSection, WriteDocxInput
                    await tool.invoke(WriteDocxInput(title=title, sections=[DocxSection(body=content)], filename=path), ctx)
                    tool_calls.append("write_docx")
            elif fmt in ("pdf", "pdf"):
                tool = self._get_tool("write_pdf")
                if tool:
                    from citnega.packages.tools.builtin.write_pdf import PDFSection, WritePDFInput
                    await tool.invoke(WritePDFInput(title=title, sections=[PDFSection(body=content)], filename=path), ctx)
                    tool_calls.append("write_pdf")
        except Exception:
            pass
