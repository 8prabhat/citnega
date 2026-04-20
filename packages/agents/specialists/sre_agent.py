"""SREAgent — incident response, log triage, runbook execution, post-mortems."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SREInput(BaseModel):
    task: str = Field(description="SRE task — e.g. 'triage this incident', 'analyze error logs', 'write post-mortem', 'check service health'.")
    log_file: str = Field(default="", description="Path to a log file to analyze.")
    error_pattern: str = Field(default="ERROR|CRITICAL|FATAL|Exception|Traceback", description="Log pattern to search for.")
    service_url: str = Field(default="", description="Service URL to health-check.")


class SREAgent(SpecialistBase):
    name = "sre_agent"
    description = (
        "Site Reliability Engineering specialist for incident triage, log analysis, "
        "runbook execution, service health checks, and post-mortem writing. "
        "Follows verify-after discipline: every action is stated, executed, then confirmed. "
        "Use for: on-call incidents, outage triage, log pattern detection, capacity checks, "
        "deployment health verification."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = SREInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior SRE. Follow runbook discipline: for every action, state what you "
        "will do, what you expect to happen, and verify after. "
        "For incidents: triage severity → scope blast radius → identify root cause → mitigate → communicate. "
        "For post-mortems: blameless timeline → contributing factors → impact → action items with owners. "
        "Never speculate without evidence from logs or monitoring. "
        "Escalate clearly when scope is beyond available tools."
    )
    TOOL_WHITELIST = [
        "log_analyzer", "run_shell", "git_ops", "read_file",
        "search_files", "api_tester", "memory_inspector", "write_kb", "read_kb",
    ]

    async def _execute(self, input: SREInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.log_file:
            log_tool = self._get_tool("log_analyzer")
            if log_tool:
                try:
                    from citnega.packages.tools.builtin.log_analyzer import LogAnalyzerInput
                    result = await log_tool.invoke(
                        LogAnalyzerInput(file_path=input.log_file, pattern=input.error_pattern, max_lines=500),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Log analysis:\n{result.get_output_field('result')}")
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
                        gathered.append(f"Service health check:\n{result.get_output_field('result')}")
                        tool_calls_made.append("api_tester")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
