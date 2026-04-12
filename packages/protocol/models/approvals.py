"""Approval Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class Approval(BaseModel):
    approval_id: str
    run_id: str
    callable_name: str
    input_summary: str  # human-readable preview
    requested_at: datetime
    responded_at: datetime | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    user_note: str | None = None
