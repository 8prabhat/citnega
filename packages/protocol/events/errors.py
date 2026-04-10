"""Error event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class ErrorEvent(BaseEvent):
    event_type: str = "ErrorEvent"
    error_code: str
    message:    str
    traceback:  str | None = None
