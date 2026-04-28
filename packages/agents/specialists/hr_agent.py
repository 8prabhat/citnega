"""HRAgent — recruitment, performance reviews, org design, onboarding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class HRInput(BaseModel):
    task: str = Field(description="HR task — e.g. 'write job description', 'create performance review', 'design onboarding plan', 'draft org chart'.")
    candidate_file: str = Field(default="", description="Path to candidate CV or profile file.")
    headcount_data: str = Field(default="", description="Path to headcount or org data file.")
    output_file: str = Field(default="", description="Output file path for generated document.")


class HRAgent(SpecialistBase):
    name = "hr_agent"
    description = (
        "Human Resources specialist for recruitment pipelines, performance reviews, "
        "org design, and onboarding plans. Follows HR best practices: STAR format "
        "for behavioral assessments, competency frameworks for evaluation, "
        "inclusive language throughout. Use for: JDs, interview guides, "
        "appraisal templates, org restructuring, new-hire programs."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = HRInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior HR Business Partner with 15+ years of experience. "
        "For performance reviews: use STAR format (Situation, Task, Action, Result). "
        "Every feedback point has a specific example and actionable development suggestion. "
        "For recruitment: structure JDs with clear requirements vs. nice-to-haves. "
        "For org design: apply spans-and-layers principles; every recommendation includes "
        "owner, timeline, and success metric. "
        "Use inclusive, bias-free language in all documents. "
        "Never include age, gender, or other protected-characteristic language in JDs. "
        "Flag any discriminatory content in inputs and refuse to reproduce it."
    )
    TOOL_WHITELIST = [
        "write_docx", "read_file", "write_file", "search_files", "email_composer",
    ]

    async def _execute(self, input: HRInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        for file_path, label in [(input.candidate_file, "Candidate data"), (input.headcount_data, "Headcount data")]:
            if file_path:
                read_tool = self._get_tool("read_file")
                if read_tool:
                    try:
                        from citnega.packages.tools.builtin.read_file import ReadFileInput
                        result = await read_tool.invoke(ReadFileInput(file_path=file_path), child_ctx)
                        if result.success:
                            gathered.append(f"{label}:\n{result.get_output_field('result')}")
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
