"""diff_compare — compare two text strings or files and return a diff."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_MODES = {"unified", "side-by-side", "summary"}


class DiffCompareInput(BaseModel):
    text_a: str = Field(default="", description="First text to compare (or leave empty if using file_a).")
    text_b: str = Field(default="", description="Second text to compare (or leave empty if using file_b).")
    file_a: str = Field(default="", description="Path to first file (used if text_a is empty).")
    file_b: str = Field(default="", description="Path to second file (used if text_b is empty).")
    mode: str = Field(default="unified", description="Diff mode: unified | side-by-side | summary")
    context_lines: int = Field(default=3, description="Lines of context around each change (unified mode).")
    label_a: str = Field(default="a", description="Label for the first version.")
    label_b: str = Field(default="b", description="Label for the second version.")


class DiffCompareTool(BaseCallable):
    """Compare two texts or files and return a formatted diff."""

    name = "diff_compare"
    description = (
        "Compare two text strings or files and return a diff. "
        "Modes: unified (standard diff format), side-by-side (columns), summary (stats only). "
        "Uses stdlib difflib — no external dependencies."
    )
    callable_type = CallableType.TOOL
    input_schema = DiffCompareInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: DiffCompareInput, context: CallContext) -> ToolOutput:
        mode = input.mode.lower().strip()
        if mode not in _VALID_MODES:
            return ToolOutput(result=f"[diff_compare: unknown mode '{mode}'. Valid: unified | side-by-side | summary]")

        # Resolve inputs
        text_a = input.text_a
        text_b = input.text_b

        if not text_a and input.file_a:
            p = Path(input.file_a).expanduser().resolve()
            if not p.exists():
                return ToolOutput(result=f"[diff_compare: file_a not found: {p}]")
            text_a = p.read_text(encoding="utf-8", errors="replace")

        if not text_b and input.file_b:
            p = Path(input.file_b).expanduser().resolve()
            if not p.exists():
                return ToolOutput(result=f"[diff_compare: file_b not found: {p}]")
            text_b = p.read_text(encoding="utf-8", errors="replace")

        if not text_a and not text_b:
            return ToolOutput(result="[diff_compare: both inputs are empty]")

        lines_a = text_a.splitlines(keepends=True)
        lines_b = text_b.splitlines(keepends=True)

        if mode == "unified":
            diff = list(difflib.unified_diff(
                lines_a, lines_b,
                fromfile=input.label_a, tofile=input.label_b,
                n=input.context_lines,
            ))
            if not diff:
                return ToolOutput(result="No differences found.")
            return ToolOutput(result="".join(diff))

        if mode == "summary":
            matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
            ratio = matcher.ratio()
            ops = matcher.get_opcodes()
            added = sum(j2 - j1 for tag, _, _, j1, j2 in ops if tag in ("insert", "replace"))
            removed = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag in ("delete", "replace"))
            unchanged = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag == "equal")
            return ToolOutput(
                result=(
                    f"Similarity: {ratio * 100:.1f}%\n"
                    f"Lines added:   {added}\n"
                    f"Lines removed: {removed}\n"
                    f"Lines unchanged: {unchanged}\n"
                    f"Total a: {len(lines_a)}  Total b: {len(lines_b)}"
                )
            )

        # side-by-side
        differ = difflib.HtmlDiff()  # reuse internal logic without HTML
        # Build side-by-side as plain text table
        sm = difflib.SequenceMatcher(None, lines_a, lines_b)
        rows: list[str] = [f"{'─'*40} {input.label_a:<20} │ {input.label_b}"]
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            a_chunk = lines_a[i1:i2]
            b_chunk = lines_b[j1:j2]
            for la, lb in zip(
                (l.rstrip() for l in a_chunk),
                (l.rstrip() for l in b_chunk),
            ):
                marker = " " if tag == "equal" else ("+" if tag == "insert" else ("-" if tag == "delete" else "~"))
                rows.append(f"{marker} {la[:50]:<50} │ {lb[:50]}")
            # Handle unequal chunk lengths
            for la in a_chunk[len(b_chunk):]:
                rows.append(f"- {la.rstrip()[:50]:<50} │")
            for lb in b_chunk[len(a_chunk):]:
                rows.append(f"+ {'':50} │ {lb.rstrip()[:50]}")

        if not any(r.startswith(("~", "+", "-")) for r in rows[1:]):
            return ToolOutput(result="No differences found.")
        return ToolOutput(result="\n".join(rows[:200]))  # cap output
