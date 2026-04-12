"""Approval flow events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class ApprovalRequestEvent(BaseEvent):
    event_type: str = "ApprovalRequestEvent"
    approval_id: str
    callable_name: str
    input_summary: str
    preview: str


class ApprovalResponseEvent(BaseEvent):
    event_type: str = "ApprovalResponseEvent"
    approval_id: str
    approved: bool
    user_note: str | None = None


class ApprovalTimeoutEvent(BaseEvent):
    event_type: str = "ApprovalTimeoutEvent"
    approval_id: str
