"""read_kb — retrieve relevant items from the knowledge base."""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy


class ReadKBInput(BaseModel):
    query:       str   = Field(description="Search query for the knowledge base.")
    max_results: int   = Field(default=5)
    tags:        list[str] = Field(default_factory=list, description="Optional tag filters.")


class ReadKBTool(BaseCallable):
    """
    Knowledge Base retrieval tool.

    Phase 2 stub: returns a placeholder message.
    Will be wired to a real IKnowledgeStore in Phase 8.
    """

    name          = "read_kb"
    description   = "Search and retrieve relevant items from the knowledge base."
    callable_type = CallableType.TOOL
    input_schema  = ReadKBInput
    output_schema = ToolOutput
    policy        = tool_policy(timeout_seconds=10.0)

    def __init__(self, *args, knowledge_store=None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(*args, **kwargs)
        self._kb = knowledge_store  # injected in Phase 8

    async def _execute(self, input: ReadKBInput, context: CallContext) -> ToolOutput:
        if self._kb is None:
            return ToolOutput(result="(Knowledge base not connected)")

        results = await self._kb.search(input.query, limit=input.max_results)
        if not results:
            return ToolOutput(result="No results found in the knowledge base.")

        lines = []
        for r in results:
            lines.append(f"[{r.item.title}] (score={r.score:.2f})\n{r.item.content[:500]}")
        return ToolOutput(result="\n\n".join(lines))
