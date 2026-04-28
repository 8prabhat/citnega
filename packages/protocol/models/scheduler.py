"""Scheduled-run models for SchedulerService."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScheduledRun(BaseModel):
    """A persisted schedule entry that fires agent runs autonomously."""

    schedule_id: str
    name: str
    # 5-field cron ("0 9 * * 1-5") or "once" for a one-shot run.
    schedule: str
    session_id: str
    prompt: str
    enabled: bool = True
    last_fired_at: datetime | None = None
    # Only used when schedule == "once"; the run fires at or after this time.
    next_fire_at: datetime | None = None
    created_at: datetime


class CreateScheduleRequest(BaseModel):
    name: str
    schedule: str
    session_id: str
    prompt: str
    enabled: bool = True
    next_fire_at: datetime | None = None
