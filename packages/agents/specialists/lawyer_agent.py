"""LawyerAgent — contract review, clause extraction, legal research synthesis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class LawyerInput(BaseModel):
    task: str = Field(description="Legal task — e.g. 'review this NDA', 'extract payment clauses', 'research GDPR obligations', 'redline this MSA'.")
    document_path: str = Field(default="", description="Path to a contract or legal document to review.")
    jurisdiction: str = Field(default="", description="Applicable jurisdiction, e.g. 'England and Wales', 'New York', 'EU'.")
    output_file: str = Field(default="", description="Optional path to write the redlined document or report.")


class LawyerAgent(SpecialistBase):
    name = "lawyer_agent"
    description = (
        "Legal analysis specialist for contract review, clause extraction, legal research, "
        "and document redlining. Covers NDAs, MSAs, employment contracts, SaaS agreements, "
        "data processing agreements, and regulatory compliance. "
        "Always notes jurisdiction and flags ambiguities. "
        "Use for: contract risk identification, clause comparison, regulatory research, "
        "GDPR/CCPA compliance, IP ownership analysis."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = LawyerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior commercial lawyer. Always state the applicable jurisdiction. "
        "For contract reviews: identify parties, scope, key obligations, termination rights, "
        "liability caps, IP ownership, data protection clauses, and dispute resolution. "
        "Flag: unusual/one-sided terms, missing standard protections, ambiguous language, "
        "and regulatory compliance gaps. "
        "For legal research: cite primary sources (statutes, case law) over secondary. "
        "Note publication date — law changes. "
        "IMPORTANT: This is legal analysis, not legal advice. "
        "Always recommend qualified legal counsel for binding decisions."
    )
    TOOL_WHITELIST = [
        "read_file", "write_docx", "write_pdf", "search_files",
        "search_web", "read_webpage", "write_kb", "read_kb",
    ]

    async def _execute(self, input: LawyerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.jurisdiction:
            gathered.append(f"Jurisdiction: {input.jurisdiction}")

        if input.document_path:
            reader = self._get_tool("read_file")
            if reader:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await reader.invoke(ReadFileInput(path=input.document_path), child_ctx)
                    if result.success:
                        gathered.append(f"Document content:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        # Check KB for prior legal research on this topic
        kb_tool = self._get_tool("read_kb")
        if kb_tool:
            try:
                from citnega.packages.tools.builtin.read_kb import ReadKBInput
                result = await kb_tool.invoke(ReadKBInput(query=input.task, max_results=3), child_ctx)
                if result.success:
                    text = result.get_output_field("result") or ""
                    if text and "not connected" not in text:
                        gathered.append(f"Prior legal research:\n{text}")
                        tool_calls_made.append("read_kb")
            except Exception:
                pass

        if input.output_file:
            gathered.append(f"Output file: {input.output_file}")

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
