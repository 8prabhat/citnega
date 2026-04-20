"""write_pdf — generate a PDF document from structured sections."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class PDFSection(BaseModel):
    heading: str = Field(default="", description="Section heading (empty for body-only paragraph).")
    body: str = Field(description="Section body text.")


class WritePDFInput(BaseModel):
    title: str = Field(description="Document title shown at the top of the PDF.")
    sections: list[PDFSection] = Field(description="Ordered list of sections to include.")
    filename: str = Field(description="Output file path, e.g. ~/Desktop/report.pdf")
    author: str = Field(default="citnega", description="Author metadata field.")
    font_size: int = Field(default=11, description="Body font size in points.")


class WritePDFTool(BaseCallable):
    """Generate a PDF document from a title and ordered sections."""

    name = "write_pdf"
    description = (
        "Create a PDF document from a title and list of sections. "
        "Each section has an optional heading and body text. "
        "Returns the path of the created file."
    )
    callable_type = CallableType.TOOL
    input_schema = WritePDFInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: WritePDFInput, context: CallContext) -> ToolOutput:
        try:
            from fpdf import FPDF  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[write_pdf: fpdf2 not installed — run: pip install fpdf2]")

        out_path = Path(input.filename).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        pdf = FPDF()
        pdf.set_author(input.author)
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=16)
        pdf.cell(0, 10, input.title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)

        for section in input.sections:
            if section.heading:
                pdf.set_font("Helvetica", style="B", size=input.font_size + 1)
                pdf.cell(0, 8, section.heading, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
            pdf.set_font("Helvetica", size=input.font_size)
            pdf.multi_cell(0, 6, section.body)
            pdf.ln(3)

        try:
            pdf.output(str(out_path))
        except Exception as exc:
            return ToolOutput(result=f"[write_pdf: failed to write: {exc}]")

        return ToolOutput(result=f"PDF created: {out_path}  ({out_path.stat().st_size} bytes)")
