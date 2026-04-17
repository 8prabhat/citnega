"""Context assembly events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class ContextAssembledEvent(BaseEvent):
    event_type: str = "ContextAssembledEvent"
    total_tokens: int
    handlers_run: list[str]
    sources_used: list[str]
    truncated: bool


class ContextTruncatedEvent(BaseEvent):
    """Emitted by TokenBudgetHandler when sources are dropped to fit the budget."""

    event_type: str = "ContextTruncatedEvent"
    before_tokens: int
    after_tokens: int
    budget_tokens: int
    dropped_sources: list[str]  # source_type strings for each dropped source
