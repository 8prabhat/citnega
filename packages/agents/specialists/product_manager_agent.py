"""ProductManagerAgent — PRDs, roadmaps, user research synthesis, competitive analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ProductManagerInput(BaseModel):
    task: str = Field(description="PM task — e.g. 'write PRD', 'build roadmap', 'synthesize user research', 'competitive analysis'.")
    context_file: str = Field(default="", description="Path to context file (research notes, data, existing spec).")
    research_query: str = Field(default="", description="Web search query for competitive/market research.")
    output_file: str = Field(default="", description="Output file path for generated document.")


class ProductManagerAgent(SpecialistBase):
    name = "product_manager_agent"
    description = (
        "Product Management specialist for PRDs, roadmap planning, user research synthesis, "
        "and competitive analysis. Follows PM best practices: RICE/ICE prioritization, "
        "user-story format with acceptance criteria, OKR alignment. "
        "Use for: feature specs, quarterly roadmaps, user research summaries, "
        "market landscape documents."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = ProductManagerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior Product Manager with strong analytical and writing skills. "
        "PRDs must include: problem statement, goals & non-goals, user stories with "
        "acceptance criteria, success metrics, and explicit 'out of scope' section. "
        "Roadmaps use RICE or ICE scoring; every item has owner and target quarter. "
        "Competitive analyses compare on: features, pricing, positioning, strengths, weaknesses. "
        "User research syntheses lead with top 3 insight themes, each backed by direct quotes. "
        "Always state assumptions explicitly and flag open questions."
    )
    TOOL_WHITELIST = [
        "write_docx", "create_ppt", "read_file", "search_web", "read_kb", "write_kb",
    ]

    async def _execute(self, input: ProductManagerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.context_file:
            read_tool = self._get_tool("read_file")
            if read_tool:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await read_tool.invoke(ReadFileInput(path=input.context_file), child_ctx)
                    if result.success:
                        gathered.append(f"Context:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        if input.research_query:
            search_tool = self._get_tool("search_web")
            if search_tool:
                try:
                    from citnega.packages.tools.builtin.search_web import SearchWebInput
                    result = await search_tool.invoke(SearchWebInput(query=input.research_query), child_ctx)
                    if result.success:
                        gathered.append(f"Research:\n{result.get_output_field('result')}")
                        tool_calls_made.append("search_web")
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
