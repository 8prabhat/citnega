"""write_file — write or append content to a file. Requires approval."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class WriteFileInput(BaseModel):
    file_path: str = Field(description="Absolute or ~-prefixed destination path.")
    content: str = Field(description="Text content to write.")
    mode: str = Field(default="write", description="'write' (overwrite) or 'append'.")
    encoding: str = Field(default="utf-8")
    make_dirs: bool = Field(default=True, description="Create parent directories if absent.")


class WriteFileTool(BaseCallable):
    name = "write_file"
    description = "Write or append text content to a file. Requires user approval."
    callable_type = CallableType.TOOL
    input_schema = WriteFileInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=True,  # writes always require approval
        allowed_paths=["${SESSION_ID}"],
        network_allowed=False,
    )

    async def _execute(self, input: WriteFileInput, context: CallContext) -> ToolOutput:
        path = pathlib.Path(input.file_path.replace("~", str(pathlib.Path.home())))
        if input.make_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        if input.mode == "append":
            with path.open("a", encoding=input.encoding) as fh:
                fh.write(input.content)
            action = "appended"
        else:
            path.write_text(input.content, encoding=input.encoding)
            action = "written"
        return ToolOutput(result=f"File {action}: {path} ({len(input.content)} chars)")
