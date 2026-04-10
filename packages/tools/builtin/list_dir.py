"""list_dir — list directory contents."""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import ArtifactError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class ListDirInput(BaseModel):
    dir_path:   str  = Field(description="Directory path to list.")
    recursive:  bool = Field(default=False, description="List recursively.")
    max_items:  int  = Field(default=200, description="Maximum items to return.")
    show_hidden: bool = Field(default=False)


class ListDirTool(BaseCallable):
    name          = "list_dir"
    description   = "List files and directories at a given path."
    callable_type = CallableType.TOOL
    input_schema  = ListDirInput
    output_schema = ToolOutput
    policy        = tool_policy(
        timeout_seconds=10.0,
        allowed_paths=["${SESSION_ID}"],
    )

    async def _execute(self, input: ListDirInput, context: CallContext) -> ToolOutput:
        path = pathlib.Path(input.dir_path.replace("~", str(pathlib.Path.home())))
        if not path.exists():
            raise ArtifactError(f"Directory not found: {path}")
        if not path.is_dir():
            raise ArtifactError(f"Not a directory: {path}")

        if input.recursive:
            items = list(path.rglob("*"))
        else:
            items = list(path.iterdir())

        if not input.show_hidden:
            items = [i for i in items if not i.name.startswith(".")]

        items = sorted(items)[:input.max_items]
        lines = []
        for item in items:
            prefix = "D" if item.is_dir() else "F"
            rel = item.relative_to(path)
            lines.append(f"[{prefix}] {rel}")

        return ToolOutput(result="\n".join(lines) if lines else "(empty)")
