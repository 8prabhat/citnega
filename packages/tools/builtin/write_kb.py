"""write_kb — add an item to the knowledge base. Requires approval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class WriteKBInput(BaseModel):
    title:   str        = Field(description="Title for this KB entry.")
    content: str        = Field(description="Content to store in the knowledge base.")
    tags:    list[str]  = Field(default_factory=list)
    source:  str        = Field(default="", description="Optional source URL or path.")


class WriteKBTool(BaseCallable):
    """
    Knowledge Base write tool.

    Phase 2 stub: returns a placeholder message.
    Will be wired to a real IKnowledgeStore in Phase 8.
    """

    name          = "write_kb"
    description   = "Add or update an item in the knowledge base. Requires user approval."
    callable_type = CallableType.TOOL
    input_schema  = WriteKBInput
    output_schema = ToolOutput
    policy        = tool_policy(
        timeout_seconds=15.0,
        requires_approval=True,
    )

    def __init__(self, *args, knowledge_store=None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(*args, **kwargs)
        self._kb = knowledge_store

    async def _execute(self, input: WriteKBInput, context: CallContext) -> ToolOutput:
        if self._kb is None:
            return ToolOutput(result="(Knowledge base not available — Phase 8)")
        return ToolOutput(result="(Knowledge base not available — Phase 8)")
