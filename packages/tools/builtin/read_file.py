"""read_file — read the contents of a file."""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy
from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.shared.errors import ArtifactError


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Absolute or ~-prefixed path to the file to read.")
    encoding: str = Field(default="utf-8", description="File encoding.")
    max_bytes: int = Field(default=256 * 1024, description="Maximum bytes to read.")


class ReadFileTool(BaseCallable):
    name          = "read_file"
    description   = "Read the contents of a file from the local filesystem."
    callable_type = CallableType.TOOL
    input_schema  = ReadFileInput
    output_schema = ToolOutput
    policy        = tool_policy(
        timeout_seconds=15.0,
        requires_approval=False,
        allowed_paths=["${SESSION_ID}"],
        network_allowed=False,
    )

    async def _execute(self, input: ReadFileInput, context: CallContext) -> ToolOutput:
        import pathlib
        path = pathlib.Path(input.file_path.replace("~", str(pathlib.Path.home())))
        if not path.exists():
            raise ArtifactError(f"File not found: {path}")
        if not path.is_file():
            raise ArtifactError(f"Path is not a file: {path}")
        raw = path.read_bytes()[:input.max_bytes]
        try:
            content = raw.decode(input.encoding, errors="replace")
        except LookupError:
            content = raw.decode("utf-8", errors="replace")
        return ToolOutput(result=content)
