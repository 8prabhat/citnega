"""Checkpoint metadata model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CheckpointMeta(BaseModel):
    checkpoint_id:  str
    session_id:     str
    run_id:         str
    created_at:     datetime
    framework_name: str
    file_path:      str    # absolute path to the checkpoint blob
    size_bytes:     int
    state_summary:  str
