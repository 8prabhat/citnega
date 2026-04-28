"""prometheus_query — execute PromQL instant and range queries."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_DEFAULT_URL = "http://localhost:9090"


class PrometheusQueryInput(BaseModel):
    query: str = Field(description="PromQL query expression.")
    query_type: str = Field(default="instant", description="Query type: 'instant' | 'range'.")
    start: str = Field(default="", description="Start time for range query (Unix timestamp or RFC3339).")
    end: str = Field(default="", description="End time for range query.")
    step: str = Field(default="60s", description="Step interval for range query (e.g. '60s', '5m').")
    max_data_points: int = Field(default=50, description="Cap returned data points.")


class PrometheusQueryTool(BaseCallable):
    name = "prometheus_query"
    description = (
        "Execute PromQL instant or range queries against a Prometheus server. "
        "Uses PROMETHEUS_URL env var (default: http://localhost:9090). "
        "Install: pip install httpx"
    )
    callable_type = CallableType.TOOL
    input_schema = PrometheusQueryInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: PrometheusQueryInput, context: CallContext) -> ToolOutput:
        try:
            import httpx
        except ImportError:
            return ToolOutput(result="[prometheus_query: httpx not installed — run: pip install httpx]")

        base_url = os.environ.get("PROMETHEUS_URL", _DEFAULT_URL).rstrip("/")

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                if input.query_type == "instant":
                    resp = await client.get(
                        f"{base_url}/api/v1/query",
                        params={"query": input.query},
                    )
                elif input.query_type == "range":
                    if not input.start or not input.end:
                        return ToolOutput(result="[prometheus_query: start and end required for range query]")
                    resp = await client.get(
                        f"{base_url}/api/v1/query_range",
                        params={
                            "query": input.query,
                            "start": input.start,
                            "end": input.end,
                            "step": input.step,
                        },
                    )
                else:
                    return ToolOutput(result=f"[prometheus_query: unknown query_type '{input.query_type}']")

                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != "success":
                    return ToolOutput(result=f"[prometheus_query: Prometheus error — {data.get('error', 'unknown')}]")

                result_type = data["data"]["resultType"]
                results = data["data"]["result"]

                if not results:
                    return ToolOutput(result=f"[prometheus_query: no data returned for '{input.query}']")

                lines = [f"Query: {input.query} | Type: {result_type} | Series: {len(results)}"]
                for series in results[:input.max_data_points]:
                    metric = series.get("metric", {})
                    label_str = ", ".join(f"{k}={v}" for k, v in metric.items())
                    if result_type == "vector":
                        ts, val = series["value"]
                        lines.append(f"  {{{label_str}}} = {val} @ {ts}")
                    elif result_type == "matrix":
                        vals = series.get("values", [])[-3:]
                        val_str = " | ".join(f"{v[1]}@{v[0]}" for v in vals)
                        lines.append(f"  {{{label_str}}} latest: {val_str}")
                    else:
                        lines.append(f"  {label_str}: {series}")
                return ToolOutput(result="\n".join(lines))

        except Exception as exc:
            return ToolOutput(result=f"[prometheus_query: {exc}]")
