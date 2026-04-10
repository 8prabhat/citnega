"""search_web — search the web using a configured search API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class SearchWebInput(BaseModel):
    query:       str = Field(description="Search query string.")
    max_results: int = Field(default=10, description="Maximum results to return.")
    safe_search: bool = Field(default=True)


class SearchWebTool(BaseCallable):
    """
    Web search tool.

    Uses DuckDuckGo Instant Answer API (no API key required) for basic
    search.  Returns title + URL + snippet per result.

    For production, replace with a proper search API (Serper, Bing, etc.)
    by overriding ``_execute()``.
    """

    name          = "search_web"
    description   = "Search the web and return title/URL/snippet results."
    callable_type = CallableType.TOOL
    input_schema  = SearchWebInput
    output_schema = ToolOutput
    policy        = tool_policy(
        timeout_seconds=20.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: SearchWebInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError as exc:
            raise CallableError("httpx not installed") from exc

        import json as _json
        import urllib.parse

        params = {
            "q": input.query,
            "format": "json",
            "no_redirect": "1",
            "no_html": "1",
        }
        if input.safe_search:
            params["safe_search"] = "strict"

        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(params)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise CallableError(f"Search failed: {exc}") from exc

        lines: list[str] = []

        # Related topics as search results
        for item in data.get("RelatedTopics", [])[: input.max_results]:
            if isinstance(item, dict) and "Text" in item:
                first_url = item.get("FirstURL", "")
                text = item["Text"]
                lines.append(f"• {text}\n  {first_url}")

        if not lines:
            # Abstract fallback
            abstract = data.get("Abstract", "")
            abstract_url = data.get("AbstractURL", "")
            if abstract:
                lines.append(f"• {abstract}\n  {abstract_url}")

        if not lines:
            return ToolOutput(result=f"No results found for: {input.query!r}")

        return ToolOutput(result=f"Search results for {input.query!r}:\n\n" + "\n\n".join(lines))
