"""edit_file — in-place file editing via exact-string replacement.

This is the primary tool for modifying existing files.  The LLM reads the
file first (read_file), identifies the exact string to replace, then calls
this tool.  Exact-match ensures surgical edits with no unintended side-effects.

Operations
----------
replace   — find *old_string* in the file and replace it with *new_string*.
            Fails if old_string appears zero times (not found) or is ambiguous
            (appears more than once and replace_all is False).
insert_after  — insert *new_string* after the given 1-indexed line number.
prepend   — insert *new_string* at the very beginning of the file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import ArtifactError
from citnega.packages.tools.builtin._tool_base import ToolOutput, resolve_file_path, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class EditFileInput(BaseModel):
    file_path: str = Field(description="Absolute or ~-prefixed path to the file to edit.")
    operation: str = Field(
        default="replace",
        description=(
            "'replace': exact-string find/replace. "
            "'insert_after': insert content after a given line number (1-indexed). "
            "'prepend': insert content at top of file."
        ),
    )
    # ── replace fields ────────────────────────────────────────────────────────
    old_string: str = Field(
        default="",
        description="Exact text to find in the file (used by 'replace').",
    )
    new_string: str = Field(
        default="",
        description="Replacement text (used by 'replace') or text to insert ('insert_after', 'prepend').",
    )
    replace_all: bool = Field(
        default=False,
        description="If True, replace every occurrence of old_string (used by 'replace').",
    )
    # ── insert_after fields ───────────────────────────────────────────────────
    line_number: int = Field(
        default=0,
        description="1-indexed line number to insert after (used by 'insert_after').",
    )
    encoding: str = Field(default="utf-8")


class EditFileTool(BaseCallable):
    name = "edit_file"
    description = (
        "Edit an existing file: replace an exact string, insert text after a line, "
        "or prepend content. Always read_file first so you have the exact text. "
        "Requires user approval."
    )
    callable_type = CallableType.TOOL
    input_schema = EditFileInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=True,
        network_allowed=False,
    )

    async def _execute(self, input: EditFileInput, context: CallContext) -> ToolOutput:
        path = resolve_file_path(input.file_path)
        if not path.exists():
            raise ArtifactError(f"File not found: {path}")
        if not path.is_file():
            raise ArtifactError(f"Path is not a file: {path}")

        original = path.read_text(encoding=input.encoding, errors="replace")
        op = input.operation

        if op == "replace":
            return self._replace(path, original, input)
        if op == "insert_after":
            return self._insert_after(path, original, input)
        if op == "prepend":
            path.write_text(input.new_string + original, encoding=input.encoding)
            return ToolOutput(result=f"Prepended {len(input.new_string)} chars to {path}")
        raise ArtifactError(
            f"Unknown operation {op!r}. Use 'replace', 'insert_after', or 'prepend'."
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _replace(path, original: str, inp: EditFileInput) -> ToolOutput:

        if not inp.old_string:
            raise ArtifactError("old_string must not be empty for 'replace' operation.")

        count = original.count(inp.old_string)
        if count == 0:
            raise ArtifactError(
                f"old_string not found in {path}.\n"
                "Tip: use read_file first to get the exact content."
            )
        if count > 1 and not inp.replace_all:
            raise ArtifactError(
                f"old_string appears {count} times in {path}. "
                "Set replace_all=True to replace all, or provide a more specific old_string."
            )

        if inp.replace_all:
            updated = original.replace(inp.old_string, inp.new_string)
            n = count
        else:
            updated = original.replace(inp.old_string, inp.new_string, 1)
            n = 1

        path.write_text(updated, encoding=inp.encoding)
        return ToolOutput(result=f"Replaced {n} occurrence(s) in {path}")

    @staticmethod
    def _insert_after(path, original: str, inp: EditFileInput) -> ToolOutput:
        if inp.line_number <= 0:
            raise ArtifactError("line_number must be >= 1 for 'insert_after'.")
        lines = original.splitlines(keepends=True)
        if inp.line_number > len(lines):
            raise ArtifactError(
                f"line_number {inp.line_number} exceeds file length ({len(lines)} lines)."
            )
        content = inp.new_string
        if content and not content.endswith("\n"):
            content += "\n"
        lines.insert(inp.line_number, content)
        path.write_text("".join(lines), encoding=inp.encoding)
        return ToolOutput(result=f"Inserted {len(inp.new_string)} chars after line {inp.line_number} in {path}")
