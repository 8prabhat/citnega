"""perf_profiler — run Python cProfile on a script and report top hotspots."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class PerfProfilerInput(BaseModel):
    script: str = Field(
        description=(
            "Path to a Python script to profile, OR a short inline Python snippet "
            "(code is written to a temp file when it contains newlines or spaces)."
        )
    )
    sort_by: str = Field(
        default="cumulative",
        description="cProfile sort key: 'cumulative', 'tottime', 'calls', 'pcalls'.",
    )
    top_n: int = Field(default=20, description="Number of top hotspot rows to return.")
    timeout: float = Field(default=30.0, description="Maximum profiling time in seconds.")


class PerfProfilerTool(BaseCallable):
    """Profile a Python script with cProfile and return the top hotspot functions."""

    name = "perf_profiler"
    description = (
        "Run Python cProfile on a script or inline snippet and return the top hotspot "
        "functions sorted by cumulative time. Useful for identifying performance bottlenecks."
    )
    callable_type = CallableType.TOOL
    input_schema = PerfProfilerInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=True,  # executes arbitrary Python code
        network_allowed=False,
        max_output_bytes=64 * 1024,
    )

    async def _execute(self, input: PerfProfilerInput, context: CallContext) -> ToolOutput:
        script_path: Path | None = None
        tmp_file: object = None

        is_inline = "\n" in input.script or not Path(input.script).exists()
        if is_inline:
            tmp_file = tempfile.NamedTemporaryFile(
                suffix=".py", mode="w", encoding="utf-8", delete=False
            )
            tmp_file.write(input.script)
            tmp_file.close()
            script_path = Path(tmp_file.name)
        else:
            script_path = Path(input.script).expanduser().resolve()
            if not script_path.exists():
                return ToolOutput(result=f"[perf_profiler: script not found: {script_path}]")

        cmd = [
            sys.executable,
            "-m",
            "cProfile",
            "-s",
            input.sort_by,
            str(script_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=input.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolOutput(
                    result=f"[perf_profiler: timed out after {input.timeout}s]"
                )
        finally:
            if is_inline and script_path and script_path.exists():
                try:
                    script_path.unlink()
                except Exception:
                    pass

        output = (stdout or b"").decode("utf-8", errors="replace")
        err = (stderr or b"").decode("utf-8", errors="replace")

        # Extract the stats table (lines after the header row)
        lines = output.splitlines()
        table_start = next(
            (i for i, l in enumerate(lines) if "ncalls" in l and "tottime" in l), 0
        )
        table_lines = lines[table_start : table_start + input.top_n + 5]

        result_parts: list[str] = []
        if err.strip():
            result_parts.append(f"stderr:\n{err[:500]}")
        result_parts.append("\n".join(table_lines) if table_lines else output[: 3000])

        return ToolOutput(result="\n\n".join(result_parts))
