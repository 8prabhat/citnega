"""RiskManagerAgent — risk identification, assessment, control mapping, risk register."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class RiskManagerInput(BaseModel):
    task: str = Field(description="Risk task — e.g. 'assess risks for project X', 'review control Y', 'update risk register', 'compliance check against ISO 27001'.")
    context: str = Field(default="", description="Project/system description, existing risk documentation, or relevant context.")
    register_file: str = Field(default="", description="Path to existing risk register (CSV/Excel) to read and update.")
    output_file: str = Field(default="", description="Optional path to write updated risk register or report.")


class RiskManagerAgent(SpecialistBase):
    name = "risk_manager_agent"
    description = (
        "Risk and control management specialist for risk identification, likelihood/impact assessment, "
        "control mapping, residual risk analysis, and compliance checks. "
        "Produces risk registers, control test reports, and heat maps. "
        "Use for: project risk assessments, IT risk reviews, compliance gap analysis, "
        "control effectiveness testing, ISO 27001 / SOC 2 / GDPR readiness."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = RiskManagerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior risk and control manager. For every risk: identify the threat, "
        "rate inherent likelihood (1–5) and impact (1–5), map to existing controls, "
        "rate residual risk, and recommend mitigation. "
        "Use standard risk register format: Risk ID | Description | Category | "
        "Likelihood | Impact | Inherent Score | Controls | Residual Score | Owner | Status. "
        "Flag CRITICAL risks (score ≥ 15) immediately. "
        "For compliance: map gaps to specific control requirements, not general principles."
    )
    TOOL_WHITELIST = [
        "read_file", "write_pdf", "write_docx", "create_excel",
        "sql_query", "pandas_analyze", "search_files", "write_kb", "read_kb",
    ]

    async def _execute(self, input: RiskManagerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.context:
            gathered.append(f"Context:\n{input.context}")

        if input.register_file:
            analyzer = self._get_tool("pandas_analyze")
            if analyzer:
                try:
                    from citnega.packages.tools.builtin.pandas_analyze import PandasAnalyzeInput
                    result = await analyzer.invoke(
                        PandasAnalyzeInput(file_path=input.register_file, operations=["head", "shape", "missing"]),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Existing risk register:\n{result.get_output_field('result')}")
                        tool_calls_made.append("pandas_analyze")
                except Exception:
                    pass

        if input.output_file:
            gathered.append(f"Output file: {input.output_file}")

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
