"""RetrieverAgent — KB, web, and file retrieval specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.agents.specialists._specialist_base import SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class RetrieverInput(BaseModel):
    query: str = Field(description="What to retrieve.")
    sources: list[str] = Field(
        default_factory=lambda: ["kb", "web"],
        description="Sources to query: 'kb', 'web', 'files'.",
    )


class RetrieverAgent(BaseAgent):
    agent_id = "retriever"
    name = "retriever_agent"
    description = "Retrieves relevant information from KB, web, and files."
    callable_type = CallableType.SPECIALIST
    input_schema = RetrieverInput
    output_schema = SpecialistOutput

    SYSTEM_PROMPT = (
        "You are a retrieval agent. Find, fetch, and summarise relevant information. "
        "Always cite sources. Never hallucinate — if not found, say so."
    )

    TOOL_WHITELIST = ["read_kb", "fetch_url", "search_web", "search_files", "read_file"]

    async def _execute(self, input: RetrieverInput, context: CallContext) -> SpecialistOutput:
        tool_results: list[str] = []

        # Try KB first
        if "kb" in input.sources:
            kb_tool = self._get_tool("read_kb")
            if kb_tool:
                try:
                    from citnega.packages.tools.builtin.read_kb import ReadKBInput

                    child_ctx = context.child(self.name, self.callable_type)
                    result = await kb_tool.invoke(ReadKBInput(query=input.query), child_ctx)
                    if result.success and result.output:
                        tool_results.append(f"[KB]\n{result.output.result}")
                except Exception:
                    pass

        # Try web search
        if "web" in input.sources:
            web_tool = self._get_tool("search_web")
            if web_tool:
                try:
                    from citnega.packages.tools.builtin.search_web import (
                        SearchWebInput,
                    )

                    child_ctx = context.child(self.name, self.callable_type)
                    result = await web_tool.invoke(SearchWebInput(query=input.query), child_ctx)
                    if result.success and result.output:
                        tool_results.append(f"[Web]\n{result.output.result}")
                except Exception:
                    pass

        gathered = "\n\n".join(tool_results) if tool_results else "No results from tools."
        user_msg = (
            f"Query: {input.query}\n\nRetrieved information:\n{gathered}\n\nSummarise the findings."
        )
        response = await self._call_model(user_msg, context)
        return SpecialistOutput(response=response, sources=input.sources)
