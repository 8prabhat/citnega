"""QAAgent — specialist for architecture/risk review and quality-gate analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class QAAgentInput(BaseModel):
    task: str = Field(
        default="Assess quality risks and propose remediation.",
        description="Quality-assurance objective.",
    )
    working_dir: str = Field(
        default="",
        description="Repository root. Empty means current working directory.",
    )
    quality_profile: str = Field(
        default="quick",
        description="quality_gate profile: quick|standard|strict.",
    )
    include_repo_map: bool = Field(
        default=True,
        description="Whether to gather architecture map context via repo_map.",
    )
    include_quality_gate: bool = Field(
        default=True,
        description="Whether to run quality_gate checks.",
    )
    include_test_matrix: bool = Field(
        default=True,
        description="Whether to gather test-suite distribution via test_matrix.",
    )
    max_findings: int = Field(
        default=10,
        description="Maximum findings to report in the final response.",
    )


class QAAgent(SpecialistBase):
    name = "qa_agent"
    description = (
        "Quality specialist: maps architecture hotspots, runs quality gates, "
        "and reports prioritized defects/risks with remediation steps."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = QAAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=240.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a senior QA and architecture reviewer.\n"
        "Prioritize correctness and regression risk over style nits.\n"
        "Return findings ordered by severity with concrete remediation steps."
    )
    TOOL_WHITELIST = ["repo_map", "quality_gate", "test_matrix", "read_file", "search_files"]

    async def _execute(self, input: QAAgentInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        sections: list[str] = []
        sources: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)

        if input.include_repo_map:
            repo_tool = self._get_tool("repo_map")
            if repo_tool is not None:
                from citnega.packages.tools.builtin.repo_map import RepoMapInput

                repo_result = await repo_tool.invoke(
                    RepoMapInput(
                        root_path=input.working_dir,
                        include_tests=True,
                        max_files=4000,
                        max_hotspots=12,
                        max_edges=15,
                    ),
                    child_ctx,
                )
                tool_calls_made.append("repo_map")
                if repo_result.success and repo_result.output:
                    out = repo_result.output
                    sections.append(
                        "Repository map:\n"
                        f"- {out.summary}\n"
                        f"- Top modules: {', '.join(out.top_modules[:6])}\n"
                        f"- Hotspots: {', '.join(out.hotspots[:6])}\n"
                        f"- Import edges: {', '.join(out.import_edges[:6])}"
                    )
                    sources.append("repo_map")
                elif repo_result.error:
                    sections.append(f"Repository map failed: {repo_result.error.message}")

        if input.include_quality_gate:
            gate_tool = self._get_tool("quality_gate")
            if gate_tool is not None:
                from citnega.packages.tools.builtin.quality_gate import QualityGateInput

                gate_result = await gate_tool.invoke(
                    QualityGateInput(
                        working_dir=input.working_dir,
                        profile=input.quality_profile,
                    ),
                    child_ctx,
                )
                tool_calls_made.append("quality_gate")
                if gate_result.success and gate_result.output:
                    out = gate_result.output
                    failing = [c.name for c in out.checks if not c.passed]
                    sections.append(
                        "Quality gate:\n"
                        f"- {out.summary}\n"
                        f"- Passed checks: {out.passed_checks}/{out.total_checks}\n"
                        f"- Failing checks: {', '.join(failing) if failing else 'none'}"
                    )
                    sources.append("quality_gate")
                elif gate_result.error:
                    sections.append(f"Quality gate failed to execute: {gate_result.error.message}")

        if input.include_test_matrix:
            matrix_tool = self._get_tool("test_matrix")
            if matrix_tool is not None:
                from citnega.packages.tools.builtin.test_matrix import MatrixInput

                matrix_result = await matrix_tool.invoke(
                    MatrixInput(
                        root_path=input.working_dir,
                        execute=False,
                    ),
                    child_ctx,
                )
                tool_calls_made.append("test_matrix")
                if matrix_result.success and matrix_result.output:
                    out = matrix_result.output
                    bucket_text = ", ".join(
                        f"{k}:{v}" for k, v in sorted(out.buckets.items())
                    ) or "none"
                    sections.append(
                        "Test matrix:\n"
                        f"- {out.summary}\n"
                        f"- Buckets: {bucket_text}"
                    )
                    sources.append("test_matrix")
                elif matrix_result.error:
                    sections.append(f"Test matrix failed to execute: {matrix_result.error.message}")

        prompt = (
            f"QA task: {input.task}\n"
            f"Max findings: {max(1, input.max_findings)}\n\n"
            "Collected evidence:\n"
            + ("\n\n".join(sections) if sections else "No tool evidence available.\n")
            + "\n\nProduce:\n"
            "1) Prioritized findings (severity high/medium/low)\n"
            "2) Why each matters (risk/regression impact)\n"
            "3) Concrete remediation steps\n"
            "4) Residual risks and missing tests"
        )

        if context.model_gateway is not None:
            response = await self._call_model(prompt, context)
        else:
            response = (
                "Model unavailable for synthesis.\n\n"
                + ("\n\n".join(sections) if sections else "No diagnostics gathered.")
            )

        return SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )
