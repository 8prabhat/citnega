"""BaseEvent — root of the canonical event hierarchy."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallableType


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class BaseEvent(BaseModel):
    """
    Root of every canonical event emitted by the Citnega runtime.

    All events share these correlation fields so that event logs,
    app logs, and invocation traces can be joined by run_id / session_id.
    """

    schema_version:  int = 1
    event_id:        str = Field(default_factory=_new_uuid)
    event_type:      str                               # class name, set by subclass
    timestamp:       datetime = Field(default_factory=_utcnow)
    session_id:      str
    run_id:          str
    turn_id:         str | None = None
    callable_name:   str | None = None
    callable_type:   CallableType | None = None
    framework_name:  str | None = None
