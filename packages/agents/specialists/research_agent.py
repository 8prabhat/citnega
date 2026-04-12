"""ResearchAgent — web search + URL fetching specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ResearchInput(BaseModel):
    query: str = Field(description="Research question or topic.")
    depth: str = Field(default="standard", description="'quick' | 'standard' | 'deep'")
    max_sources: int = Field(default=5)


class ResearchAgent(SpecialistBase):
    name = "research_agent"
    description = "Researches topics via web search and URL fetching."
    callable_type = CallableType.SPECIALIST
    input_schema = ResearchInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a research specialist. Given a query, you search the web, "
        "fetch relevant pages, and synthesise a well-sourced answer. "
        "Always cite your sources. Be concise but comprehensive."
    )
    TOOL_WHITELIST = ["search_web", "fetch_url"]

    async def _execute(self, input: ResearchInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        sources: list[str] = []

        # Step 1: search the web
        search_tool = self._get_tool("search_web")
        search_results = ""
        if search_tool:
            from citnega.packages.tools.builtin.search_web import SearchWebInput

            child_ctx = context.child(self.name, self.callable_type)
            result = await search_tool.invoke(
                SearchWebInput(query=input.query, max_results=input.max_sources),
                child_ctx,
            )
            if result.success and result.output:
                search_results = result.output.result  # type: ignore[attr-defined]
                tool_calls_made.append("search_web")

        # Step 2: synthesise via model
        prompt = f"Research query: {input.query}\n\nSearch results:\n{search_results}\n\nSynthesise a response."
        response = await self._call_model(prompt, context)

        return SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )
