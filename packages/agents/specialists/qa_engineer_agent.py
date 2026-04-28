"""QAEngineerAgent — test planning, coverage analysis, quality gate enforcement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class QAEngineerInput(BaseModel):
    task: str = Field(description="QA task — e.g. 'review test coverage', 'write test plan', 'run test suite', 'find untested paths'.")
    working_dir: str = Field(default="", description="Repository root or working directory path.")
    test_files: list[str] = Field(default_factory=list, description="Specific test file paths to analyze.")
    run_tests: bool = Field(default=False, description="If True, execute test suite and quality gate.")


class QAEngineerAgent(SpecialistBase):
    name = "qa_engineer_agent"
    description = (
        "QA Engineer specialist for test planning, coverage analysis, "
        "test suite execution, and quality gate enforcement. "
        "Tests are independent, repeatable, and deterministic. "
        "Always runs quality_gate before marking work done. "
        "Use for: coverage gap analysis, test plan writing, CI test strategy, "
        "regression test reviews."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = QAEngineerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a senior QA engineer with expertise in test strategy and automation. "
        "Every test must be: independent (no shared mutable state), repeatable "
        "(same result on every run), deterministic (no time/random dependencies). "
        "Coverage analysis must cite file:line for uncovered paths. "
        "Test plans include: scope, out-of-scope, test types (unit/integration/e2e), "
        "entry/exit criteria, risk areas, and test data requirements. "
        "Before declaring work done, always run quality_gate and address any failures. "
        "Flag flaky tests explicitly — they are worse than no tests."
    )
    TOOL_WHITELIST = [
        "run_shell", "read_file", "search_files", "api_tester", "test_matrix", "quality_gate",
    ]

    async def _execute(self, input: QAEngineerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.run_tests and input.working_dir:
            matrix_tool = self._get_tool("test_matrix")
            if matrix_tool:
                try:
                    from citnega.packages.tools.builtin.test_matrix import MatrixInput
                    result = await matrix_tool.invoke(
                        MatrixInput(root_path=input.working_dir, execute=True),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Test matrix results:\n{result.get_output_field('result')}")
                        tool_calls_made.append("test_matrix")
                except Exception:
                    pass

            gate_tool = self._get_tool("quality_gate")
            if gate_tool:
                try:
                    from citnega.packages.tools.builtin.quality_gate import QualityGateInput
                    result = await gate_tool.invoke(
                        QualityGateInput(working_dir=input.working_dir),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Quality gate:\n{result.get_output_field('result')}")
                        tool_calls_made.append("quality_gate")
                except Exception:
                    pass

        for test_file in input.test_files[:5]:
            read_tool = self._get_tool("read_file")
            if read_tool:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await read_tool.invoke(ReadFileInput(path=test_file), child_ctx)
                    if result.success:
                        gathered.append(f"Test file {test_file}:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
