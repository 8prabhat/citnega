"""UXDesignAgent — design critiques, wireframe specs, usability testing plans."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class UXDesignInput(BaseModel):
    task: str = Field(description="UX task — e.g. 'critique this design', 'write wireframe spec', 'plan usability test', 'review information architecture'.")
    design_file: str = Field(default="", description="Path to design file, screenshot, or spec document.")
    url: str = Field(default="", description="URL to fetch for live UI review.")


class UXDesignAgent(SpecialistBase):
    name = "ux_design_agent"
    description = (
        "UX Design specialist for design critiques, wireframe specifications, "
        "and usability testing plans. Applies Nielsen's 10 heuristics and "
        "WCAG accessibility principles. "
        "Use for: heuristic evaluations, screen flow specs, usability test scripts, "
        "information architecture reviews."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = UXDesignInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior UX designer with expertise in interaction design and accessibility. "
        "Design critiques apply Nielsen's 10 heuristics (visibility, match real world, "
        "user control, consistency, error prevention, recognition over recall, "
        "flexibility, aesthetic minimalism, error recovery, help & docs). "
        "Every critique issue has: heuristic violated, severity (1-4), specific example, "
        "and recommended fix. "
        "Wireframe specs cover: screen name, layout grid, components with states, "
        "interactions (hover, click, focus), edge cases (empty state, error state, loading). "
        "Usability test plans include: research questions, participant criteria, "
        "tasks with success criteria, facilitation notes, metrics to capture."
    )
    TOOL_WHITELIST = [
        "read_file", "write_file", "fetch_url", "read_kb", "write_kb",
    ]

    async def _execute(self, input: UXDesignInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.design_file:
            read_tool = self._get_tool("read_file")
            if read_tool:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await read_tool.invoke(ReadFileInput(path=input.design_file), child_ctx)
                    if result.success:
                        gathered.append(f"Design file:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        if input.url:
            fetch_tool = self._get_tool("fetch_url")
            if fetch_tool:
                try:
                    from citnega.packages.tools.builtin.fetch_url import FetchURLInput
                    result = await fetch_tool.invoke(FetchURLInput(url=input.url), child_ctx)
                    if result.success:
                        gathered.append(f"Live page content:\n{result.get_output_field('result')}")
                        tool_calls_made.append("fetch_url")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
