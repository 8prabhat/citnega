"""Context assembly models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from citnega.packages.protocol.models.model_gateway import ModelMessage


class ContextSource(BaseModel):
    """A single enrichment contribution to the context object."""

    source_type: str     # "recent_turns" | "summary" | "kb" | "state"
    content:     str
    token_count: int
    metadata:    dict[str, object] = Field(default_factory=dict)


class ContextObject(BaseModel):
    """Fully assembled context passed to the framework runner for a turn."""

    session_id:      str
    run_id:          str
    user_input:      str
    sources:         list[ContextSource] = Field(default_factory=list)
    total_tokens:    int = 0
    assembled_at:    datetime
    budget_remaining: int
    truncated:       bool = False

    # Structured message history populated by ConversationContextHandler.
    # When present, framework runners should use this instead of ``sources``
    # to build the prompt — it carries proper role/content structure.
    messages:         list[dict[str, Any]] = Field(default_factory=list)
    # Active model ID — set by ConversationContextHandler from ConversationStore
    active_model_id:  str | None = None
