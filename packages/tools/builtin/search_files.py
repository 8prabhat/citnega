"""search_files — search file contents with regex or glob pattern."""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import ArtifactError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class SearchFilesInput(BaseModel):
    root_path:      str  = Field(description="Root directory to search under.")
    pattern:        str  = Field(description="Regex pattern to search for in file content.")
    glob_filter:    str  = Field(default="**/*", description="Glob filter for file names.")
    max_results:    int  = Field(default=50)
    context_lines:  int  = Field(default=2, description="Lines of context around each match.")
    case_sensitive: bool = Field(default=False)


class SearchFilesTool(BaseCallable):
    name          = "search_files"
    description   = "Search file contents matching a regex pattern within a directory tree."
    callable_type = CallableType.TOOL
    input_schema  = SearchFilesInput
    output_schema = ToolOutput
    policy        = tool_policy(
        timeout_seconds=30.0,
        allowed_paths=["${SESSION_ID}"],
    )

    async def _execute(self, input: SearchFilesInput, context: CallContext) -> ToolOutput:
        root = pathlib.Path(input.root_path.replace("~", str(pathlib.Path.home())))
        if not root.exists():
            raise ArtifactError(f"Search root not found: {root}")

        flags = 0 if input.case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(input.pattern, flags)
        except re.error as exc:
            raise ArtifactError(f"Invalid regex pattern: {exc}") from exc

        results: list[str] = []
        for file_path in root.glob(input.glob_filter):
            if not file_path.is_file():
                continue
            try:
                lines = file_path.read_text(errors="replace").splitlines()
            except (OSError, PermissionError):
                continue

            for i, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, i - input.context_lines)
                    end   = min(len(lines), i + input.context_lines + 1)
                    snippet = "\n".join(
                        f"  {j+1:>4}: {lines[j]}" for j in range(start, end)
                    )
                    rel = file_path.relative_to(root)
                    results.append(f"{rel}:{i+1}\n{snippet}")
                    if len(results) >= input.max_results:
                        break
            if len(results) >= input.max_results:
                break

        if not results:
            return ToolOutput(result="No matches found.")
        return ToolOutput(result=f"{len(results)} match(es):\n\n" + "\n\n".join(results))
