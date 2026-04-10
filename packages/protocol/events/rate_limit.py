"""Rate limit event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class RateLimitEvent(BaseEvent):
    event_type:   str = "RateLimitEvent"
    provider:     str
    wait_seconds: float
