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


class RunTerminalReasonEvent(BaseEvent):
    """
    Emitted immediately before RunCompleteEvent to explain *why* the run
    reached its terminal state.

    Fields
    ------
    reason
        Short machine-readable reason code:
        ``"completed"`` | ``"cancelled"`` | ``"failed"`` |
        ``"depth_limit"`` | ``"timeout"`` | ``"approval_denied"``
    details
        Human-readable explanation (exception message, policy detail, etc.).
        Empty string when the run completed normally.
    """

    event_type: str = "RunTerminalReasonEvent"
    reason: str
    details: str = ""
