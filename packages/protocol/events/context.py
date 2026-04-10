"""Context assembly event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class ContextAssembledEvent(BaseEvent):
    event_type:   str = "ContextAssembledEvent"
    total_tokens: int
    handlers_run: list[str]
    sources_used: list[str]
    truncated:    bool
