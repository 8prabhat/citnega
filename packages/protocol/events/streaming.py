"""Streaming token event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class TokenEvent(BaseEvent):
    """Emitted for each LLM token during streaming."""

    event_type: str = "TokenEvent"
    token:      str
    is_first:   bool = False
    is_final:   bool = False
