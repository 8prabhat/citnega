"""api_tester — test REST API endpoints and validate responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class APITesterInput(BaseModel):
    url: str = Field(description="Full URL to request (e.g. https://api.example.com/v1/status).")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, PATCH, DELETE.")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers to include (e.g. {'Authorization': 'Bearer token'}).",
    )
    body: str = Field(default="", description="Request body (JSON string for POST/PUT).")
    expected_status: int = Field(
        default=200, description="Expected HTTP status code. Returns PASS/FAIL verdict."
    )
    timeout: float = Field(default=15.0, description="Request timeout in seconds.")


class APITesterTool(BaseCallable):
    """Send an HTTP request to a REST endpoint and validate the response."""

    name = "api_tester"
    description = (
        "Send an HTTP request to a REST API endpoint and inspect the response. "
        "Returns status code, response headers, body (truncated), and a PASS/FAIL verdict "
        "against the expected status code. Useful for API smoke tests, health checks, "
        "and verifying service behavior."
    )
    callable_type = CallableType.TOOL
    input_schema = APITesterInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=64 * 1024,
    )

    async def _execute(self, input: APITesterInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError:
            return ToolOutput(
                result="[api_tester: httpx not installed — run: pip install httpx]"
            )

        method = input.method.upper()
        headers = dict(input.headers)
        body_bytes = input.body.encode("utf-8") if input.body else None

        if body_bytes and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=input.timeout, follow_redirects=True) as client:
                response = await client.request(
                    method,
                    input.url,
                    headers=headers,
                    content=body_bytes,
                )
        except httpx.TimeoutException:
            return ToolOutput(result=f"[api_tester: request timed out after {input.timeout}s]")
        except httpx.RequestError as exc:
            return ToolOutput(result=f"[api_tester: connection error: {exc}]")

        verdict = "PASS" if response.status_code == input.expected_status else "FAIL"
        body_preview = response.text[:2000]
        if len(response.text) > 2000:
            body_preview += f"\n… (truncated, {len(response.text)} total chars)"

        resp_headers = "\n".join(
            f"  {k}: {v}" for k, v in list(response.headers.items())[:10]
        )

        return ToolOutput(
            result=(
                f"URL: {input.url}\n"
                f"Method: {method}\n"
                f"Status: {response.status_code} (expected {input.expected_status}) — {verdict}\n"
                f"Response headers:\n{resp_headers}\n"
                f"Body:\n{body_preview}"
            )
        )
