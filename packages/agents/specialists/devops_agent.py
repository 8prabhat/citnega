"""DevOpsAgent — CI/CD pipelines, infrastructure automation, deployment health."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DevOpsInput(BaseModel):
    task: str = Field(description="DevOps task — e.g. 'debug deployment failure', 'write CI pipeline', 'check service health', 'analyze build logs'.")
    repo_path: str = Field(default="", description="Path to repository root.")
    log_file: str = Field(default="", description="Path to CI/build log file.")
    service_url: str = Field(default="", description="Service endpoint URL for health check.")


class DevOpsAgent(SpecialistBase):
    name = "devops_agent"
    description = (
        "DevOps engineer specialist for CI/CD debugging, infrastructure automation, "
        "build pipeline analysis, and deployment health verification. "
        "Follows verify-after discipline for all shell operations. "
        "Use for: pipeline failures, deployment debugging, Docker/Kubernetes config, "
        "GitHub Actions / GitLab CI authoring, infrastructure-as-code review."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = DevOpsInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a senior DevOps engineer with expertise in CI/CD, containers, and IaC. "
        "Verify-after discipline: for every shell command, state what you expect to happen, "
        "execute it, and confirm the outcome matches. "
        "Read the full log file before diagnosing — never guess at partial output. "
        "For deployment failures: check exit codes → check logs → check dependencies → "
        "check environment → check network. "
        "For pipeline authoring: every job has explicit dependencies, timeouts, "
        "and failure notifications. "
        "Never store secrets in scripts, Dockerfiles, or CI configs — use environment variables "
        "or secret manager references. "
        "Provide rollback steps whenever recommending a deployment change."
    )
    TOOL_WHITELIST = [
        "run_shell", "read_file", "write_file", "git_ops", "api_tester", "log_analyzer",
    ]

    async def _execute(self, input: DevOpsInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.log_file:
            log_tool = self._get_tool("log_analyzer")
            if log_tool:
                try:
                    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput
                    result = await log_tool.invoke(
                        LogAnalyzerInput(file_path=input.log_file, max_lines=1000),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Build/CI log analysis:\n{result.get_output_field('result')}")
                        tool_calls_made.append("log_analyzer")
                except Exception:
                    pass

        if input.service_url:
            api_tool = self._get_tool("api_tester")
            if api_tool:
                try:
                    from citnega.packages.tools.builtin.api_tester import APITesterInput
                    result = await api_tool.invoke(APITesterInput(url=input.service_url), child_ctx)
                    if result.success:
                        gathered.append(f"Service health:\n{result.get_output_field('result')}")
                        tool_calls_made.append("api_tester")
                except Exception:
                    pass

        if input.repo_path:
            git_tool = self._get_tool("git_ops")
            if git_tool:
                try:
                    from citnega.packages.tools.builtin.git_ops import GitOpsInput
                    result = await git_tool.invoke(
                        GitOpsInput(command="status", repo_path=input.repo_path),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Repo status:\n{result.get_output_field('result')}")
                        tool_calls_made.append("git_ops")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
