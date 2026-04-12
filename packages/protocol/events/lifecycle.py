"""Run lifecycle events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent
from citnega.packages.protocol.models.runs import RunState


class RunStateEvent(BaseEvent):
    """Emitted on every RunState transition."""

    event_type: str = "RunStateEvent"
    from_state: RunState
    to_state: RunState
    reason: str | None = None


class RunCompleteEvent(BaseEvent):
    """
    Sentinel event — signals consumers to stop draining the event queue.
    Always the last event in a run's event stream.
    """

    event_type: str = "RunCompleteEvent"
    final_state: RunState
