"""MLEngineerAgent — ML pipeline implementation, model packaging, deployment prep."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class MLEngineerInput(BaseModel):
    task: str = Field(description="ML engineering task — e.g. 'package model for serving', 'write training pipeline', 'profile inference performance', 'audit dependencies'.")
    project_path: str = Field(default="", description="Root path of the ML project.")
    model_file: str = Field(default="", description="Path to a model file or training script to review.")


class MLEngineerAgent(SpecialistBase):
    name = "ml_engineer_agent"
    description = (
        "ML engineering specialist for training pipelines, model packaging, serving infrastructure, "
        "performance profiling, and MLOps. Can write pipeline code, audit dependencies, "
        "profile inference latency, and prepare deployment artefacts. "
        "Use for: pipeline implementation, model serving setup, performance bottlenecks, "
        "dependency security, reproducibility reviews."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = MLEngineerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior ML engineer. Focus on production-readiness: "
        "reproducibility (pin dependencies, seed random), efficiency (vectorise, batch), "
        "observability (log metrics, artefacts), and safety (validate inputs, handle edge cases). "
        "Write clean Python with type hints. Prefer scikit-learn, PyTorch, or MLflow conventions. "
        "Always profile before optimising — show evidence from perf_profiler output."
    )
    TOOL_WHITELIST = [
        "run_shell", "read_file", "write_file", "git_ops",
        "perf_profiler", "dependency_auditor", "pandas_analyze", "write_kb", "read_kb",
    ]

    async def _execute(self, input: MLEngineerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.project_path:
            dep_tool = self._get_tool("dependency_auditor")
            if dep_tool:
                try:
                    from citnega.packages.tools.builtin.dependency_auditor import DependencyAuditorInput
                    result = await dep_tool.invoke(DependencyAuditorInput(path=input.project_path), child_ctx)
                    if result.success:
                        gathered.append(f"Dependency audit:\n{result.get_output_field('result')}")
                        tool_calls_made.append("dependency_auditor")
                except Exception:
                    pass

        if input.model_file:
            reader = self._get_tool("read_file")
            if reader:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await reader.invoke(ReadFileInput(path=input.model_file), child_ctx)
                    if result.success:
                        gathered.append(f"Model/script content:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
