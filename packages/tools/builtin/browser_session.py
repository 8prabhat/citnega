"""browser_session — Playwright browser automation: navigate, click, fill, screenshot, extract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class BrowserSessionInput(BaseModel):
    action: str = Field(description="Action: 'navigate' | 'click' | 'fill' | 'screenshot' | 'extract'")
    url: str = Field(default="", description="URL to navigate to.")
    selector: str = Field(default="", description="CSS selector for click/fill/extract.")
    value: str = Field(default="", description="Value to fill into a form field.")
    output_path: str = Field(default="", description="File path to save screenshot.")
    timeout: float = Field(default=30.0, description="Action timeout in seconds.")


class BrowserSessionTool(BaseCallable):
    name = "browser_session"
    description = (
        "Playwright browser automation: navigate to URLs, click elements, fill forms, "
        "take screenshots, and extract DOM text. Handles JavaScript-rendered pages and auth flows."
    )
    callable_type = CallableType.TOOL
    input_schema = BrowserSessionInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: BrowserSessionInput, context: CallContext) -> ToolOutput:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ToolOutput(result="[browser_session: playwright not installed — run: pip install playwright && playwright install]")

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    if input.action == "navigate":
                        if not input.url:
                            return ToolOutput(result="[browser_session: url is required for navigate]")
                        await page.goto(input.url, timeout=int(input.timeout * 1000))
                        title = await page.title()
                        return ToolOutput(result=f"Navigated to {input.url}\nPage title: {title}")

                    elif input.action == "click":
                        if input.url:
                            await page.goto(input.url, timeout=int(input.timeout * 1000))
                        if not input.selector:
                            return ToolOutput(result="[browser_session: selector is required for click]")
                        await page.click(input.selector, timeout=int(input.timeout * 1000))
                        return ToolOutput(result=f"Clicked selector: {input.selector}")

                    elif input.action == "fill":
                        if input.url:
                            await page.goto(input.url, timeout=int(input.timeout * 1000))
                        if not input.selector:
                            return ToolOutput(result="[browser_session: selector is required for fill]")
                        await page.fill(input.selector, input.value, timeout=int(input.timeout * 1000))
                        return ToolOutput(result=f"Filled {input.selector!r} with value.")

                    elif input.action == "screenshot":
                        if input.url:
                            await page.goto(input.url, timeout=int(input.timeout * 1000))
                        path = input.output_path or "/tmp/browser_screenshot.png"
                        await page.screenshot(path=path, full_page=True)
                        return ToolOutput(result=f"Screenshot saved to: {path}")

                    elif input.action == "extract":
                        if input.url:
                            await page.goto(input.url, timeout=int(input.timeout * 1000))
                        if input.selector:
                            elements = await page.query_selector_all(input.selector)
                            texts = [await el.inner_text() for el in elements[:20]]
                            return ToolOutput(result="\n".join(texts))
                        else:
                            text = await page.inner_text("body")
                            return ToolOutput(result=text[:8000])

                    else:
                        return ToolOutput(result=f"[browser_session: unknown action '{input.action}']")

                finally:
                    await browser.close()

        except Exception as exc:
            return ToolOutput(result=f"[browser_session: {exc}]")
