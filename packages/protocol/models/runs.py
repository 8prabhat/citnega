"""Run-related Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class RunState(StrEnum):
    PENDING = "pending"
    CONTEXT_ASSEMBLING = "context_assembling"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Set of terminal states — a run in one of these cannot be resumed.
TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.CANCELLED,
    }
)

#: Valid state transitions (from → {allowed targets}).
VALID_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.PENDING: frozenset({RunState.CONTEXT_ASSEMBLING, RunState.CANCELLED}),
    RunState.CONTEXT_ASSEMBLING: frozenset(
        {RunState.EXECUTING, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.EXECUTING: frozenset(
        {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.WAITING_APPROVAL,
            RunState.PAUSED,
        }
    ),
    RunState.WAITING_APPROVAL: frozenset({RunState.EXECUTING, RunState.FAILED, RunState.CANCELLED}),
    RunState.PAUSED: frozenset({RunState.EXECUTING, RunState.CANCELLED}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


class RunSummary(BaseModel):
    """Persisted summary of a completed or in-progress run."""

    run_id: str
    session_id: str
    started_at: datetime
    finished_at: datetime | None = None
    state: RunState
    turn_count: int = 0
    total_tokens: int = 0
    error: str | None = None
    # Stored so stale PENDING runs can be replayed after a process restart.
    user_input: str | None = None


class StateSnapshot(BaseModel):
    """Point-in-time snapshot of a session's runtime state."""

    session_id: str
    current_run_id: str | None
    active_callable: str | None
    run_state: RunState
    context_token_count: int
    checkpoint_available: bool
    framework_name: str
    captured_at: datetime
