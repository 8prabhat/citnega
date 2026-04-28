"""TraceSpan — lightweight structured span for a single tool/agent invocation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TraceSpan:
    span_id: str
    run_id: str
    turn_id: str | None
    step_id: str | None
    tool_name: str
    start_ts: str
    end_ts: str
    input_hash: str
    output_hash: str
    success: bool
