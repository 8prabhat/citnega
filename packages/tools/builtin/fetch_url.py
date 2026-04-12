"""fetch_url — fetch the content of a URL. Requires approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class FetchURLInput(BaseModel):
    url: str = Field(description="URL to fetch.")
    method: str = Field(default="GET", description="HTTP method.")
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = Field(default="", description="Request body (for POST/PUT).")
    timeout: float = Field(default=20.0)
    max_bytes: int = Field(default=256 * 1024, description="Max response bytes.")
    extract_text: bool = Field(default=True, description="Strip HTML tags if True.")


class FetchURLTool(BaseCallable):
    name = "fetch_url"
    description = "Fetch content from a URL via HTTP/HTTPS. Requires user approval."
    callable_type = CallableType.TOOL
    input_schema = FetchURLInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: FetchURLInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError as exc:
            raise CallableError("httpx not installed") from exc

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=input.timeout) as client:
                resp = await client.request(
                    input.method.upper(),
                    input.url,
                    headers=input.headers,
                    content=input.body.encode() if input.body else None,
                )
            raw = resp.content[: input.max_bytes]
            text = raw.decode(resp.encoding or "utf-8", errors="replace")

            if input.extract_text and "html" in resp.headers.get("content-type", "").lower():
                import re

                text = re.sub(r"<[^>]+>", "", text)
                text = re.sub(r"\s{2,}", " ", text).strip()

            return ToolOutput(result=f"HTTP {resp.status_code}\n{text}")
        except httpx.HTTPError as exc:
            raise CallableError(f"HTTP error fetching {input.url}: {exc}") from exc
