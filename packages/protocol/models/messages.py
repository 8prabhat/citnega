"""Message Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"
    TOOL      = "tool"


class Message(BaseModel):
    message_id: str
    session_id: str
    run_id:     str | None = None
    role:       MessageRole
    content:    str
    timestamp:  datetime
    metadata:   dict[str, object] = Field(default_factory=dict)
