"""ResearchAgent — web search + URL fetching specialist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ResearchInput(BaseModel):
    query: str = Field(description="Research question or topic to investigate.")
    depth: str = Field(
        default="standard",
        description=(
            "'quick' for a fast single-search answer, "
            "'standard' for search + read top article (default), "
            "'deep' for search + read top 3 articles."
        ),
    )
    max_sources: int = Field(default=5)


class ResearchAgent(SpecialistBase):
    name = "research_agent"
    description = (
        "Research, fact-check, or get current information on ANY topic. "
        "Use this for: current events, geopolitics, conflicts, news, sports scores, "
        "prices, software releases, people, companies, or anything that may have "
        "changed recently. It searches the web, reads full article content, and "
        "synthesises a well-sourced answer combining current facts with analysis. "
        "Prefer this over raw search for any research or factual question."
    )
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
        "You are a research specialist. Your job is to produce accurate, current, "
        "well-sourced answers by combining web search results with your analysis.\n\n"
        "For any question about ongoing situations (geopolitics, conflicts, economics, "
        "sports, technology): first establish the CURRENT state via search, then provide "
        "reasoning and context. Never answer 'what is the logic/reasoning behind X' "
        "without first finding out what X currently looks like.\n\n"
        "Always cite sources. Be concise but comprehensive. "
        "Distinguish clearly between current facts (from search) and analysis (your reasoning)."
    )
    TOOL_WHITELIST = ["search_web", "read_webpage", "fetch_url", "get_datetime", "write_kb", "read_kb"]

    async def _execute(self, input: ResearchInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        sources: list[str] = []

        child_ctx = context.child(self.name, self.callable_type)

        # Step -1: check KB for prior research on this topic
        kb_prior_context = ""
        kb_read_tool = self._get_tool("read_kb")
        if kb_read_tool:
            try:
                from citnega.packages.tools.builtin.read_kb import ReadKBInput

                kb_result = await kb_read_tool.invoke(
                    ReadKBInput(query=input.query, max_results=3), child_ctx
                )
                if kb_result.success and kb_result.output:
                    kb_text = kb_result.get_output_field("result")
                    if kb_text and "(Knowledge base not connected)" not in kb_text:
                        kb_prior_context = kb_text
                        tool_calls_made.append("read_kb")
            except Exception:
                pass  # KB unavailable — proceed without it

        # Step 0: get current date so the model knows what "latest" means
        datetime_context = ""
        datetime_tool = self._get_tool("get_datetime")
        if datetime_tool:
            from citnega.packages.tools.builtin.get_datetime import GetDatetimeInput

            dt_result = await datetime_tool.invoke(GetDatetimeInput(), child_ctx)
            if dt_result.success and dt_result.output:
                datetime_context = dt_result.get_output_field("result")
                tool_calls_made.append("get_datetime")

        # Step 1: search the web
        search_tool = self._get_tool("search_web")
        search_results = ""
        result_urls: list[str] = []
        if search_tool:
            from citnega.packages.tools.builtin.search_web import SearchWebInput

            result = await search_tool.invoke(
                SearchWebInput(query=input.query, max_results=input.max_sources),
                child_ctx,
            )
            if result.success and result.output:
                search_results = result.get_output_field("result")
                tool_calls_made.append("search_web")
                # Extract URLs for follow-up fetching
                import re
                result_urls = re.findall(r"URL: (https?://\S+)", search_results)

        # Step 2: fetch content from top URLs for deeper context (skip on 'quick')
        page_contents: list[str] = []
        if input.depth != "quick":
            read_tool = self._get_tool("read_webpage")
            fetch_limit = 3 if input.depth == "deep" else 1
            if read_tool and result_urls:
                from citnega.packages.tools.builtin.read_webpage import ReadWebpageInput

                for url in result_urls[:fetch_limit]:
                    sources.append(url)
                    page_result = await read_tool.invoke(
                        ReadWebpageInput(url=url, max_chars=4000), child_ctx
                    )
                    if page_result.success and page_result.output:
                        page_contents.append(page_result.get_output_field("result"))
                if page_contents:
                    tool_calls_made.append("read_webpage")

        # Step 3: synthesise via model with all gathered context
        sections = []
        if kb_prior_context:
            sections.append(f"Prior research from knowledge base:\n{kb_prior_context}")
        if datetime_context:
            sections.append(f"Current date/time:\n{datetime_context}")
        sections.append(f"Search results:\n{search_results}")
        for i, content in enumerate(page_contents, 1):
            sections.append(f"Page {i} content:\n{content}")

        prompt = (
            f"Research query: {input.query}\n\n"
            + "\n\n---\n\n".join(sections)
            + "\n\nSynthesise an accurate, well-sourced response based on the above. "
            "Use the current date context to judge whether information is up to date."
        )
        response = await self._call_model(prompt, context)

        return SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )
