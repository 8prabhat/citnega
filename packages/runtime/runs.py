"""RunManager — state machine and persistence for run lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
import uuid

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.models.runs import (
    TERMINAL_RUN_STATES,
    VALID_RUN_TRANSITIONS,
    RunState,
    RunSummary,
)
from citnega.packages.shared.errors import RunNotFoundError
from citnega.packages.shared.errors import RuntimeError as CitnegaRuntimeError

if TYPE_CHECKING:
    from citnega.packages.storage.repositories.run_repo import RunRepository


class InvalidTransitionError(CitnegaRuntimeError):
    error_code = "RUNTIME_INVALID_TRANSITION"


class RunManager:
    """Thin facade over RunRepository that enforces FSM transitions."""

    def __init__(self, run_repo: RunRepository) -> None:
        self._repo = run_repo

    async def create(self, session_id: str, user_input: str | None = None) -> RunSummary:
        run = RunSummary(
            run_id=str(uuid.uuid4()),
            session_id=session_id,
            state=RunState.PENDING,
            started_at=datetime.now(tz=UTC),
            user_input=user_input,
        )
        await self._repo.save(run)
        runtime_logger.info(
            "run_created",
            run_id=run.run_id,
            session_id=session_id,
        )
        return run

    async def get(self, run_id: str) -> RunSummary:
        run = await self._repo.get(run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id!r} not found.")
        return run

    async def transition(
        self,
        run_id: str,
        new_state: RunState,
        *,
        error: str | None = None,
        tokens: int | None = None,
    ) -> RunSummary:
        """Apply a validated state transition and persist."""
        run = await self.get(run_id)
        allowed = VALID_RUN_TRANSITIONS.get(run.state, frozenset())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Run {run_id!r}: transition {run.state.value!r} → "
                f"{new_state.value!r} is not allowed."
            )

        updates: dict[str, object] = {"state": new_state}
        if new_state in TERMINAL_RUN_STATES:
            updates["finished_at"] = datetime.now(tz=UTC)
        if error is not None:
            updates["error"] = error
        if tokens is not None:
            updates["total_tokens"] = run.total_tokens + tokens

        updated = run.model_copy(update=updates)
        await self._repo.save(updated)
        runtime_logger.debug(
            "run_state_transition",
            run_id=run_id,
            from_state=run.state.value,
            to_state=new_state.value,
        )
        return updated

    async def increment_turn(self, run_id: str) -> RunSummary:
        run = await self.get(run_id)
        updated = run.model_copy(update={"turn_count": run.turn_count + 1})
        await self._repo.save(updated)
        return updated

    async def list_for_session(self, session_id: str, limit: int = 50) -> list[RunSummary]:
        return await self._repo.list(session_id=session_id, limit=limit)

    async def list_stale(self) -> list[RunSummary]:
        """Return runs stuck in PENDING/EXECUTING from a previous process."""
        return await self._repo.list_stale()

    async def cleanup_stale_runs(self) -> list[RunSummary]:
        """
        Transition stale PENDING/EXECUTING runs to FAILED on startup.

        Returns the list of runs that were cleaned up so the caller can
        optionally re-enqueue them.
        """
        stale = await self._repo.list_stale()
        for run in stale:
            try:
                # Force-update to FAILED bypassing the FSM guard — the run
                # may be in a state that doesn't allow a normal transition
                # (e.g. EXECUTING → FAILED is allowed, PENDING → FAILED is not).
                # We patch the stored state directly.
                cleaned = run.model_copy(
                    update={
                        "state": RunState.FAILED,
                        "error": "process_restart: run interrupted by shutdown",
                        "finished_at": datetime.now(tz=UTC),
                    }
                )
                await self._repo.save(cleaned)
                runtime_logger.warning(
                    "stale_run_cleaned",
                    run_id=run.run_id,
                    session_id=run.session_id,
                    was_state=run.state.value,
                )
            except Exception as exc:
                runtime_logger.error(
                    "stale_run_cleanup_failed",
                    run_id=run.run_id,
                    error=str(exc),
                )
        return stale
