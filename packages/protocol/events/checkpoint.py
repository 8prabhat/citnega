"""Checkpoint event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class CheckpointEvent(BaseEvent):
    event_type:    str = "CheckpointEvent"
    checkpoint_id: str
    file_path:     str
