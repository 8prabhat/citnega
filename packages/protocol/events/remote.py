"""Remote execution lifecycle events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class RemoteExecutionEvent(BaseEvent):
    """
    Emitted by orchestrators/workers around remote dispatch and verification.

    phase
        dispatch | verified | complete
    verification_result
        verified | failed | skipped
    """

    event_type: str = "RemoteExecutionEvent"
    phase: str
    worker_id: str = ""
    envelope_id: str = ""
    target_callable: str
    verification_result: str = "skipped"
    details: str = ""
