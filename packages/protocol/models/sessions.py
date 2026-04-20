"""Session-related Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from citnega.packages.strategy.models import StrategySpec


class SessionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class SessionConfig(BaseModel):
    """Immutable configuration that defines a session."""

    session_id: str
    name: str
    framework: str  # "adk" | "langgraph" | "crewai"
    default_model_id: str
    local_only: bool = True
    max_callable_depth: int = 2
    approval_required_tools: list[str] = Field(default_factory=list)
    kb_enabled: bool = True
    max_context_tokens: int = 8192
    approval_timeout_seconds: float = 300
    tags: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """Live session record — config + mutable runtime state."""

    config: SessionConfig
    created_at: datetime
    last_active_at: datetime
    run_count: int = 0
    state: SessionState = SessionState.IDLE
    strategy_spec: StrategySpec | None = None
