"""web_scraper — extract text, links, or tables from a web page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_EXTRACT = {"text", "links", "table"}


class WebScraperInput(BaseModel):
    url: str = Field(description="URL of the page to scrape.")
    extract: str = Field(
        default="text",
        description="What to extract: text | links | table",
    )
    css_selector: str = Field(
        default="",
        description="Optional CSS selector to scope extraction (e.g. 'article', '#main', '.content').",
    )
    max_items: int = Field(default=50, description="Max items to return (links, table rows, or text lines).")
    table_index: int = Field(default=0, description="Which table to extract when extract=table (0-based).")


class WebScraperTool(BaseCallable):
    """Scrape a web page — extract visible text, hyperlinks, or a data table."""

    name = "web_scraper"
    description = (
        "Scrape a web page and extract: text (visible body text), "
        "links (all href URLs with anchor text), or table (first/nth HTML table as markdown). "
        "Optionally scope extraction with a CSS selector."
    )
    callable_type = CallableType.TOOL
    input_schema = WebScraperInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: WebScraperInput, context: CallContext) -> ToolOutput:
        try:
            import httpx  # already a core dep
            from bs4 import BeautifulSoup  # type: ignore[import-untyped]
        except ImportError as e:
            missing = "beautifulsoup4" if "bs4" in str(e) else str(e)
            return ToolOutput(result=f"[web_scraper: {missing} not installed — run: pip install beautifulsoup4]")

        extract = input.extract.lower().strip()
        if extract not in _VALID_EXTRACT:
            return ToolOutput(result=f"[web_scraper: unknown extract '{extract}'. Valid: text | links | table]")

        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(
                    input.url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; citnega-scraper/1.0)"},
                )
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            return ToolOutput(result=f"[web_scraper: fetch error: {exc}]")

        soup = BeautifulSoup(html, "html.parser")

        # Scope to selector if provided
        root = soup
        if input.css_selector:
            scoped = soup.select_one(input.css_selector)
            if scoped:
                root = scoped

        if extract == "text":
            # Remove script/style noise
            for tag in root(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            lines = [line.strip() for line in root.get_text(separator="\n").splitlines() if line.strip()]
            shown = lines[: input.max_items]
            truncation = f"\n…({len(lines) - input.max_items} more lines)" if len(lines) > input.max_items else ""
            return ToolOutput(result="\n".join(shown) + truncation)

        if extract == "links":
            anchors = root.find_all("a", href=True)
            results = []
            for a in anchors[: input.max_items]:
                href = a["href"].strip()
                text = a.get_text(strip=True)[:80]
                results.append(f"[{text}]({href})")
            truncation = f"\n…({len(anchors) - input.max_items} more links)" if len(anchors) > input.max_items else ""
            return ToolOutput(result=f"{len(anchors)} link(s) found\n\n" + "\n".join(results) + truncation)

        # extract == "table"
        tables = root.find_all("table")
        if not tables:
            return ToolOutput(result="[web_scraper: no HTML tables found on this page]")
        idx = min(input.table_index, len(tables) - 1)
        table = tables[idx]

        rows_out: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if cells:
                rows_out.append(cells)

        if not rows_out:
            return ToolOutput(result="[web_scraper: table found but empty]")

        # Build markdown table
        header = rows_out[0]
        sep = ["---"] * len(header)
        body = rows_out[1: input.max_items + 1]
        md_lines = [
            f"| {' | '.join(header)} |",
            f"| {' | '.join(sep)} |",
        ] + [f"| {' | '.join(r)} |" for r in body]
        truncation = f"\n…({len(rows_out) - 1 - input.max_items} more rows)" if len(rows_out) - 1 > input.max_items else ""
        return ToolOutput(
            result=f"Table {idx + 1}/{len(tables)} from {input.url}\n\n" + "\n".join(md_lines) + truncation
        )
