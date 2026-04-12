"""search_web — search the web using DuckDuckGo (no API key required)."""

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
    max_results: int = Field(default=8, description="Maximum results to return.")
    safe_search: bool = Field(default=True)


class SearchWebTool(BaseCallable):
    """
    Web search tool using DuckDuckGo (no API key required).

    Tries the Instant Answer JSON API first; falls back to scraping the
    DuckDuckGo HTML results page when the API returns nothing useful.
    """

    name = "search_web"
    description = "Search the web and return title/URL/snippet results."
    callable_type = CallableType.TOOL
    input_schema = SearchWebInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=20.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: SearchWebInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError:
            return ToolOutput(result="httpx is not installed — cannot search the web.")

        lines: list[str] = []

        # ── Attempt 1: Instant Answer API ─────────────────────────────────
        try:
            params = {
                "q": input.query,
                "format": "json",
                "no_redirect": "1",
                "no_html": "1",
            }
            if input.safe_search:
                params["safe_search"] = "strict"

            url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(params)
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "citnega/1.0"})
                resp.raise_for_status()
                data = resp.json()

            # Abstract (best result)
            abstract = data.get("AbstractText") or data.get("Abstract", "")
            abstract_url = data.get("AbstractURL", "")
            if abstract:
                lines.append(f"• {abstract}\n  {abstract_url}")

            # Related topics
            for item in data.get("RelatedTopics", [])[: input.max_results]:
                if isinstance(item, dict) and "Text" in item:
                    first_url = item.get("FirstURL", "")
                    lines.append(f"• {item['Text']}\n  {first_url}")
        except Exception:
            pass  # fall through to HTML scrape

        # ── Attempt 2: HTML scrape ─────────────────────────────────────────
        if not lines:
            try:
                html_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
                    {"q": input.query}
                )
                async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                    resp = await client.get(
                        html_url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/120.0 Safari/537.36"
                            )
                        },
                    )
                    html = resp.text

                # Extract snippets: <a class="result__snippet">…</a>
                snippets = re.findall(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL
                )
                urls = re.findall(r'<a[^>]*class="result__url"[^>]*>(.*?)</a>', html, re.DOTALL)
                titles = re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)

                def _strip(s: str) -> str:
                    return re.sub(r"<[^>]+>", "", s).strip()

                count = min(input.max_results, len(snippets))
                for i in range(count):
                    title = _strip(titles[i]) if i < len(titles) else ""
                    snippet = _strip(snippets[i])
                    url = _strip(urls[i]) if i < len(urls) else ""
                    entry = f"• {title}\n  {snippet}"
                    if url:
                        entry += f"\n  {url}"
                    lines.append(entry)
            except Exception as exc:
                return ToolOutput(result=f"Search failed: {exc}")

        if not lines:
            return ToolOutput(result=f"No results found for: {input.query!r}")

        return ToolOutput(result=f"Search results for {input.query!r}:\n\n" + "\n\n".join(lines))
