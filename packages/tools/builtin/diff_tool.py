"""DiffTool — unified diff between two files or raw strings."""

from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class DiffInput(BaseModel):
    file_a: str = ""
    file_b: str = ""
    text_a: str = ""
    text_b: str = ""
    context_lines: int = 3
    label_a: str = "a"
    label_b: str = "b"


class DiffOutput(BaseModel):
    diff_text: str
    additions: int
    deletions: int
    is_identical: bool


class DiffTool(BaseCallable):
    name = "diff"
    description = (
        "Compute a unified diff between two files or two raw strings. "
        "Provide file_a/file_b for file paths or text_a/text_b for inline text."
    )
    callable_type = CallableType.TOOL
    input_schema = DiffInput
    output_schema = DiffOutput

    async def _execute(self, input_data: DiffInput, context: object) -> DiffOutput:
        if input_data.file_a or input_data.file_b:
            lines_a = Path(input_data.file_a).read_text(encoding="utf-8").splitlines(keepends=True) if input_data.file_a else []
            lines_b = Path(input_data.file_b).read_text(encoding="utf-8").splitlines(keepends=True) if input_data.file_b else []
            label_a = input_data.file_a or input_data.label_a
            label_b = input_data.file_b or input_data.label_b
        else:
            lines_a = input_data.text_a.splitlines(keepends=True)
            lines_b = input_data.text_b.splitlines(keepends=True)
            label_a = input_data.label_a
            label_b = input_data.label_b

        diff_lines = list(
            difflib.unified_diff(
                lines_a, lines_b,
                fromfile=label_a, tofile=label_b,
                n=input_data.context_lines,
            )
        )
        diff_text = "".join(diff_lines)
        additions = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
        deletions = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))

        return DiffOutput(
            diff_text=diff_text,
            additions=additions,
            deletions=deletions,
            is_identical=len(diff_lines) == 0,
        )
