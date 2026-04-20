"""memory_inspector — inspect, search, and stat the knowledge base."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class MemoryInspectorInput(BaseModel):
    action: Literal["list", "search", "stats"] = Field(
        default="list",
        description="'list' all KB entries, 'search' by keyword, or 'stats' for summary counts.",
    )
    query: str = Field(default="", description="Search keyword (used when action='search').")
    max_results: int = Field(default=20, description="Maximum entries to return.")


class MemoryInspectorTool(BaseCallable):
    """Inspect the knowledge base — list entries, search by keyword, or get statistics."""

    name = "memory_inspector"
    description = (
        "Inspect the knowledge base (KB). Use 'list' to see all stored entries, "
        "'search' to find entries matching a keyword, or 'stats' to get counts. "
        "Useful before running research to avoid duplicating prior work."
    )
    callable_type = CallableType.TOOL
    input_schema = MemoryInspectorInput
    output_schema = ToolOutput
    policy = tool_policy(timeout_seconds=10.0, requires_approval=False, network_allowed=False)

    async def _execute(self, input: MemoryInspectorInput, context: CallContext) -> ToolOutput:
        kb = getattr(context, "knowledge_store", None) or getattr(
            getattr(context, "session_config", None), "knowledge_store", None
        )
        if kb is None:
            return ToolOutput(result="(Knowledge base not connected — no entries to inspect)")

        try:
            if input.action == "stats":
                all_entries = kb.list_all() if hasattr(kb, "list_all") else []
                total = len(all_entries)
                return ToolOutput(result=f"Knowledge base: {total} entry/entries stored.")

            if input.action == "search":
                entries = (
                    kb.search(input.query, max_results=input.max_results)
                    if hasattr(kb, "search")
                    else []
                )
                if not entries:
                    return ToolOutput(result=f"No KB entries matching '{input.query}'.")
                lines = [f"- {getattr(e, 'title', str(e))}" for e in entries]
                return ToolOutput(result="\n".join(lines))

            # default: list
            entries = kb.list_all() if hasattr(kb, "list_all") else []
            if not entries:
                return ToolOutput(result="Knowledge base is empty.")
            entries = entries[: input.max_results]
            lines = [f"- {getattr(e, 'title', str(e))}" for e in entries]
            return ToolOutput(result=f"KB entries ({len(lines)}):\n" + "\n".join(lines))
        except Exception as exc:
            return ToolOutput(result=f"[memory_inspector error: {exc}]")
