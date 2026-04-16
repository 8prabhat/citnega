"""Runner-level models used by IFrameworkRunner typed methods."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationStats(BaseModel):
    """Conversation statistics returned by IFrameworkRunner.get_conversation_stats()."""

    message_count: int = 0
    token_estimate: int = 0
    compaction_count: int = 0


class ThinkingConfig(BaseModel):
    """Thinking override state for a session runner."""

    enabled: bool | None = Field(
        default=None,
        description="True = force on, False = force off, None = auto (model default).",
    )
