"""mermaid_render — render Mermaid diagram text to SVG or PNG."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class MermaidRenderInput(BaseModel):
    diagram_text: str = Field(description="Mermaid diagram source text.")
    output_format: str = Field(default="svg", description="Output format: 'svg' or 'png'.")
    output_path: str = Field(default="", description="Output file path. Defaults to a temp file.")


class MermaidRenderTool(BaseCallable):
    name = "mermaid_render"
    description = (
        "Render a Mermaid (or PlantUML) diagram definition to SVG or PNG. "
        "Requires mermaid-js CLI (mmdc): npm install -g @mermaid-js/mermaid-cli"
    )
    callable_type = CallableType.TOOL
    input_schema = MermaidRenderInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: MermaidRenderInput, context: CallContext) -> ToolOutput:
        fmt = input.output_format.lower()
        if fmt not in ("svg", "png"):
            return ToolOutput(result=f"[mermaid_render: unsupported format '{fmt}' — use 'svg' or 'png']")

        if not input.diagram_text.strip():
            return ToolOutput(result="[mermaid_render: diagram_text is empty]")

        try:
            result = subprocess.run(
                ["mmdc", "--version"],
                capture_output=True, timeout=5,
            )
            if result.returncode != 0:
                raise FileNotFoundError
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ToolOutput(
                result="[mermaid_render: mmdc not found — install with: npm install -g @mermaid-js/mermaid-cli]"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "diagram.mmd"
            input_file.write_text(input.diagram_text, encoding="utf-8")

            out_path = input.output_path or str(Path(tmpdir) / f"output.{fmt}")

            try:
                proc = subprocess.run(
                    ["mmdc", "-i", str(input_file), "-o", out_path, "-f", fmt],
                    capture_output=True,
                    timeout=25,
                    text=True,
                )
                if proc.returncode != 0:
                    return ToolOutput(result=f"[mermaid_render: mmdc error — {proc.stderr[:500]}]")

                if input.output_path:
                    return ToolOutput(result=f"Diagram rendered to: {out_path}")

                # If no output path, read SVG and return inline
                if fmt == "svg":
                    content = Path(out_path).read_text(encoding="utf-8")
                    return ToolOutput(result=f"SVG output ({len(content)} chars):\n{content[:4096]}")
                else:
                    return ToolOutput(result=f"PNG rendered to temp path: {out_path} (provide output_path to save permanently)")

            except subprocess.TimeoutExpired:
                return ToolOutput(result="[mermaid_render: render timed out after 25 seconds]")
            except Exception as exc:
                return ToolOutput(result=f"[mermaid_render: {exc}]")
