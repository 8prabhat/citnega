"""read_webpage — fetch a URL and return clean, readable text.

Unlike fetch_url (which requires approval), this tool is read-only and
autonomous.  It is intended for the model to follow up on search results
without asking the user every time.

Uses BeautifulSoup to extract clean text (removes scripts, styles, nav, etc.).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_MAX_CHARS = 6_000   # enough for a full article, not so much it bloats context
_NOISE_TAGS = {
    "script", "style", "noscript", "nav", "footer", "header",
    "aside", "form", "button", "iframe", "svg", "img",
    "meta", "link", "head",
}


class ReadWebpageInput(BaseModel):
    url: str = Field(description="Full URL to fetch (http or https).")
    max_chars: int = Field(
        default=_MAX_CHARS,
        description="Maximum characters of extracted text to return.",
    )


class ReadWebpageTool(BaseCallable):
    """
    Read-only URL fetcher that returns clean, human-readable text.

    Does NOT require user approval — it only GETs public pages.
    Used internally by research_agent to read full articles after search.

    llm_direct_access = False: the LLM uses research_agent, which calls
    this tool as part of its multi-step research pipeline.
    """

    name = "read_webpage"
    llm_direct_access = False  # agent-internal; LLM uses research_agent
    description = (
        "Fetch a URL and return its readable text content. "
        "Use this after search_web to read a full article and get accurate, current details. "
        "Does NOT require approval — it is read-only."
    )
    callable_type = CallableType.TOOL
    input_schema = ReadWebpageInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=25.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=512 * 1024,
    )

    async def _execute(self, input: ReadWebpageInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError:
            return ToolOutput(result="httpx is not installed.")

        url = input.url.strip()
        if not url.startswith(("http://", "https://")):
            return ToolOutput(result=f"Invalid URL (must start with http/https): {url!r}")

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                resp = await client.get(url)
        except Exception as exc:
            return ToolOutput(result=f"Failed to fetch {url}: {exc}")

        if resp.status_code >= 400:
            return ToolOutput(result=f"HTTP {resp.status_code} for {url}")

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return ToolOutput(result=f"Non-text response ({content_type}) — cannot extract text.")

        raw = resp.text

        # ── Extract with BeautifulSoup if available ───────────────────────────
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup.find_all(_NOISE_TAGS):
                tag.decompose()

            # Prefer article/main content
            for selector in ("article", "main", '[role="main"]', ".article-body", "#content"):
                block = soup.select_one(selector)
                if block:
                    text = block.get_text(separator="\n", strip=True)
                    break
            else:
                text = soup.get_text(separator="\n", strip=True)

        except ImportError:
            # Fallback: simple regex stripping
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"&[a-z]+;", " ", text)

        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()

        if not text:
            return ToolOutput(result=f"No readable text found at {url}")

        truncated = text[: input.max_chars]
        suffix = f"\n\n[… content truncated at {input.max_chars} chars]" if len(text) > input.max_chars else ""
        return ToolOutput(result=f"Content from {url}:\n\n{truncated}{suffix}")
