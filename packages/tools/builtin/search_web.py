"""search_web — web search using the duckduckgo-search library.

Strategy (most → least reliable):
  1. duckduckgo-search Python library (structured JSON, most stable)
  2. DuckDuckGo Instant Answer JSON API (good for factual/entity queries)
  3. DuckDuckGo HTML scrape (last resort, fragile)

No API key required for any of these.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
import urllib.parse

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SearchWebInput(BaseModel):
    query: str = Field(description="Search query string.")
    max_results: int = Field(default=8, description="Maximum results to return (1-20).")
    region: str = Field(
        default="wt-wt",
        description="Region code for results, e.g. 'in-en' for India, 'us-en' for USA.",
    )
    search_type: str = Field(
        default="text",
        description="'text' for general search, 'news' for recent news results.",
    )


class SearchWebTool(BaseCallable):
    """
    Web search via DuckDuckGo.  Uses the duckduckgo-search library for
    reliable, structured results.  Falls back to the Instant Answer API
    and then to HTML scraping if the library is unavailable.

    Returns title, snippet, and URL for each result.

    llm_direct_access = False: the LLM should call research_agent instead.
    search_web is used internally by research_agent and other specialists.
    """

    name = "search_web"
    llm_direct_access = False  # agent-internal; LLM uses research_agent
    description = (
        "Search the web and return title/URL/snippet results. "
        "Use search_type='news' for recent news, scores, and current events. "
        "Always call this for anything time-sensitive or that may have changed since training."
    )
    callable_type = CallableType.TOOL
    input_schema = SearchWebInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=25.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: SearchWebInput, context: CallContext) -> ToolOutput:
        max_r = max(1, min(20, input.max_results))

        # ── Strategy 1: duckduckgo-search library ─────────────────────────────
        try:
            results = await self._ddgs_search(input.query, max_r, input.region, input.search_type)
            if results:
                return ToolOutput(result=self._format(input.query, results))
        except Exception:
            pass

        # ── Strategy 2: Instant Answer JSON API ───────────────────────────────
        try:
            results = await self._instant_answer(input.query, max_r)
            if results:
                return ToolOutput(result=self._format(input.query, results))
        except Exception:
            pass

        # ── Strategy 3: HTML scrape ────────────────────────────────────────────
        try:
            results = await self._html_scrape(input.query, max_r)
            if results:
                return ToolOutput(result=self._format(input.query, results))
        except Exception as exc:
            return ToolOutput(result=f"All search strategies failed: {exc}")

        return ToolOutput(result=f"No results found for: {input.query!r}")

    # ── Strategy implementations ──────────────────────────────────────────────

    async def _ddgs_search(
        self, query: str, max_r: int, region: str, search_type: str
    ) -> list[dict]:
        """Use the duckduckgo-search library (most reliable)."""
        import asyncio
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]

        def _run() -> list[dict]:
            with DDGS() as ddgs:
                if search_type == "news":
                    items = list(ddgs.news(query, region=region, max_results=max_r))
                    return [
                        {
                            "title": i.get("title", ""),
                            "url": i.get("url", ""),
                            "snippet": i.get("body", ""),
                            "date": i.get("date", ""),
                            "source": i.get("source", ""),
                        }
                        for i in items
                    ]
                else:
                    items = list(ddgs.text(query, region=region, max_results=max_r))
                    return [
                        {
                            "title": i.get("title", ""),
                            "url": i.get("href", ""),
                            "snippet": i.get("body", ""),
                        }
                        for i in items
                    ]

        # DDGS is synchronous; run in thread executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run)

    async def _instant_answer(self, query: str, max_r: int) -> list[dict]:
        """DuckDuckGo Instant Answer JSON API — good for entity/fact queries."""
        import httpx

        params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(params)

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "citnega/1.0"})
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []
        abstract = data.get("AbstractText") or data.get("Abstract", "")
        abstract_url = data.get("AbstractURL", "")
        if abstract:
            results.append({"title": data.get("Heading", ""), "url": abstract_url, "snippet": abstract})

        for item in data.get("RelatedTopics", [])[:max_r]:
            if isinstance(item, dict) and "Text" in item:
                results.append(
                    {"title": "", "url": item.get("FirstURL", ""), "snippet": item["Text"]}
                )
        return results

    async def _html_scrape(self, query: str, max_r: int) -> list[dict]:
        """Last-resort HTML scraping — fragile but needs no library."""
        import httpx

        html_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        async with httpx.AsyncClient(timeout=14.0, follow_redirects=True) as client:
            resp = await client.get(
                html_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    )
                },
            )
            html = resp.text

        def _strip(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s).strip()

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)

        results = []
        for i in range(min(max_r, len(snippets))):
            results.append(
                {
                    "title": _strip(titles[i]) if i < len(titles) else "",
                    "url": _strip(urls[i]) if i < len(urls) else "",
                    "snippet": _strip(snippets[i]),
                }
            )
        return results

    # ── Formatter ─────────────────────────────────────────────────────────────

    @staticmethod
    def _format(query: str, results: list[dict]) -> str:
        lines = [f"Search results for {query!r}:\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "").strip()
            url = r.get("url", "").strip()
            snippet = r.get("snippet", "").strip()
            date = r.get("date", "")
            source = r.get("source", "")

            parts = [f"{i}. {title}" if title else f"{i}."]
            if date or source:
                meta = " | ".join(filter(None, [source, date]))
                parts.append(f"   [{meta}]")
            if snippet:
                parts.append(f"   {snippet}")
            if url:
                parts.append(f"   URL: {url}")
            lines.append("\n".join(parts))

        lines.append(
            "\nTip: use read_webpage(url=...) on any URL above to get the full article content."
        )
        return "\n\n".join(lines)
