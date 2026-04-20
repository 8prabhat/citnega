"""log_analyzer — parse log files and detect patterns, anomalies, and error spikes."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class LogAnalyzerInput(BaseModel):
    file_path: str = Field(description="Path to the log file to analyze.")
    pattern: str = Field(
        default=r"ERROR|WARN|CRITICAL|FATAL|Exception|Traceback",
        description="Regex pattern to match lines of interest.",
    )
    max_lines: int = Field(
        default=500,
        description="Maximum number of lines to read (reads from end of file when tail=True).",
    )
    tail: bool = Field(
        default=True,
        description="If True, read from the end of the file (most recent entries first).",
    )
    context_lines: int = Field(
        default=0,
        description="Number of surrounding lines to include around each match.",
    )


class LogAnalyzerTool(BaseCallable):
    """Analyze a log file — detect errors, warnings, and anomalies by pattern matching."""

    name = "log_analyzer"
    description = (
        "Read and analyze a log file for errors, warnings, and patterns. "
        "Returns matching lines with line numbers and a frequency summary. "
        "Use this to diagnose application failures, service errors, or unexpected behavior."
    )
    callable_type = CallableType.TOOL
    input_schema = LogAnalyzerInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=128 * 1024,
    )

    async def _execute(self, input: LogAnalyzerInput, context: CallContext) -> ToolOutput:
        path = Path(input.file_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[log_analyzer: file not found: {path}]")
        if not path.is_file():
            return ToolOutput(result=f"[log_analyzer: not a file: {path}]")

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return ToolOutput(result=f"[log_analyzer: read error: {exc}]")

        all_lines = text.splitlines()
        if input.tail and len(all_lines) > input.max_lines:
            all_lines = all_lines[-input.max_lines :]
            line_offset = max(0, len(text.splitlines()) - input.max_lines)
        else:
            all_lines = all_lines[: input.max_lines]
            line_offset = 0

        try:
            pattern = re.compile(input.pattern, re.IGNORECASE)
        except re.error as exc:
            return ToolOutput(result=f"[log_analyzer: invalid pattern: {exc}]")

        matches: list[tuple[int, str]] = []
        for i, line in enumerate(all_lines):
            if pattern.search(line):
                matches.append((line_offset + i + 1, line))

        if not matches:
            return ToolOutput(
                result=f"No lines matching '{input.pattern}' found in {path.name} "
                f"(scanned {len(all_lines)} lines)."
            )

        # Frequency summary by match group
        keyword_counts: Counter[str] = Counter()
        for _, line in matches:
            for kw in re.findall(input.pattern, line, re.IGNORECASE):
                keyword_counts[kw.upper()] += 1

        summary_parts = [f"{kw}={count}" for kw, count in keyword_counts.most_common(8)]
        summary = ", ".join(summary_parts)

        # Format results (cap at 50 matches for readability)
        shown = matches[:50]
        lines_out = [f"  L{lineno}: {line.rstrip()}" for lineno, line in shown]
        truncation = f"\n  … ({len(matches) - 50} more matches)" if len(matches) > 50 else ""

        return ToolOutput(
            result=(
                f"Log: {path.name} | {len(matches)} match(es) | Summary: {summary}\n"
                + "\n".join(lines_out)
                + truncation
            )
        )
