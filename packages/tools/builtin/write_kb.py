"""write_kb — add an item to the knowledge base. Requires approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class WriteKBInput(BaseModel):
    title: str = Field(description="Title for this KB entry.")
    content: str = Field(description="Content to store in the knowledge base.")
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="", description="Optional source URL or path.")


class WriteKBTool(BaseCallable):
    """
    Knowledge Base write tool.

    Phase 2 stub: returns a placeholder message.
    Will be wired to a real IKnowledgeStore in Phase 8.
    """

    name = "write_kb"
    description = "Add or update an item in the knowledge base. Requires user approval."
    callable_type = CallableType.TOOL
    input_schema = WriteKBInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=15.0,
        requires_approval=True,
    )

    def __init__(self, *args, knowledge_store=None, **kwargs) -> None:  # type: ignore[override]
        super().__init__(*args, **kwargs)
        self._kb = knowledge_store

    async def _execute(self, input: WriteKBInput, context: CallContext) -> ToolOutput:
        if self._kb is None:
            return ToolOutput(result="Knowledge base is not available.")

        from datetime import UTC, datetime
        import hashlib
        import uuid

        from citnega.packages.protocol.models.kb import KBItem, KBSourceType

        content_hash = hashlib.sha256(input.content.encode("utf-8", errors="replace")).hexdigest()
        now = datetime.now(tz=UTC)
        item = KBItem(
            item_id=str(uuid.uuid4()),
            title=input.title,
            content=input.content,
            source_type=KBSourceType.NOTE,
            source_session_id=context.session_id,
            source_run_id=context.run_id,
            tags=input.tags,
            created_at=now,
            updated_at=now,
            content_hash=content_hash,
            file_path=input.source or None,
        )
        saved = await self._kb.add_item(item)
        return ToolOutput(
            result=f"Saved to knowledge base: '{saved.title}' (id={saved.item_id[:8]})"
        )
