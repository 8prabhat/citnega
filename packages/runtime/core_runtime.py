"""
CoreRuntime — the central runtime implementing IRuntime.

Responsibilities:
  - Session lifecycle (create, list)
  - Turn execution FSM (PENDING → CONTEXT_ASSEMBLING → EXECUTING → terminal)
  - Per-session asyncio.Lock (one active run invariant)
  - Callable registration
  - Delegation to IContextAssembler and IFrameworkAdapter
  - Backpressure-aware event emission
  - Clean shutdown

FSM transitions (enforced by RunManager):
  PENDING → CONTEXT_ASSEMBLING → EXECUTING → COMPLETED | FAILED | CANCELLED
  EXECUTING → WAITING_APPROVAL → EXECUTING
  EXECUTING → PAUSED → EXECUTING
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING
import uuid

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.events.lifecycle import (
    RunCompleteEvent,
    RunStateEvent,
    RunTerminalReasonEvent,
)
from citnega.packages.protocol.interfaces.runtime import IRuntime
from citnega.packages.protocol.models.runs import RunState, RunSummary, StateSnapshot
from citnega.packages.shared.errors import (
    RunNotFoundError,
)
from citnega.packages.shared.errors import (
    RuntimeError as CitnegaRuntimeError,
)

if TYPE_CHECKING:
    from citnega.packages.capabilities.registry import CapabilityRegistry
    from citnega.packages.execution.engine import ExecutionEngine
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.types import CallableMetadata
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.interfaces.adapter import IFrameworkAdapter, IFrameworkRunner
    from citnega.packages.protocol.interfaces.context import IContextAssembler
    from citnega.packages.protocol.models.sessions import Session, SessionConfig
    from citnega.packages.runtime.events.emitter import EventEmitter
    from citnega.packages.runtime.runs import RunManager
    from citnega.packages.runtime.sessions import SessionManager
    from citnega.packages.shared.registry import BaseRegistry


class _ActiveRun:
    """Book-keeping for a single in-flight run."""

    __slots__ = ("cancelled", "run_id", "runner", "session_id", "task")

    def __init__(
        self,
        run_id: str,
        session_id: str,
        task: asyncio.Task[None],
        runner: IFrameworkRunner,
    ) -> None:
        self.run_id = run_id
        self.session_id = session_id
        self.task = task
        self.runner = runner
        self.cancelled = False


class CoreRuntime(IRuntime):
    """
    Platform-agnostic runtime.

    All external dependencies are injected at construction time so that
    tests can substitute stubs without touching bootstrap.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        run_manager: RunManager,
        context_assembler: IContextAssembler,
        framework_adapter: IFrameworkAdapter,
        event_emitter: EventEmitter,
        callable_registry: BaseRegistry[IInvocable],
        model_gateway: object | None = None,
        capability_registry: CapabilityRegistry | None = None,
        execution_engine: ExecutionEngine | None = None,
    ) -> None:
        self._sessions = session_manager
        self._runs = run_manager
        self._assembler = context_assembler
        self._adapter = framework_adapter
        self._emitter = event_emitter
        self._registry = callable_registry
        self._model_gateway = model_gateway
        self._capability_registry = capability_registry
        self._execution_engine = execution_engine
        self._runners: dict[str, IFrameworkRunner] = {}

        # Per-session lock: only one active run at a time per session
        self._session_locks: dict[str, asyncio.Lock] = {}
        # session_id → active _ActiveRun
        self._active: dict[str, _ActiveRun] = {}
        # Protect the _active dict from concurrent access
        self._active_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create_session(self, config: SessionConfig) -> Session:
        session = await self._sessions.create(config)
        # Eagerly create the framework runner for this session
        runner = await self._create_runner(session)
        # We stash the runner on the session lock entry
        async with self._active_lock:
            if config.session_id not in self._session_locks:
                self._session_locks[config.session_id] = asyncio.Lock()
        self._runners[config.session_id] = runner
        return session

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    async def run_turn(self, session_id: str, user_input: str) -> str:
        """
        Start a new turn.  Returns the run_id immediately; execution
        happens in a background asyncio.Task.

        Raises RuntimeError if a run is already active for this session.
        """
        session = await self._sessions.get(session_id)

        async with self._active_lock:
            if session_id in self._active:
                active_run_id = self._active[session_id].run_id
                raise CitnegaRuntimeError(
                    f"Session {session_id!r} already has an active run "
                    f"({active_run_id!r}).  Cancel or wait for it to finish."
                )

        # Create the run record (PENDING state)
        run = await self._runs.create(session_id)
        run_id = run.run_id
        turn_id = str(uuid.uuid4())

        # Ensure we have a session lock
        async with self._active_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()

        runner = getattr(self, "_runners", {}).get(session_id)
        if runner is None:
            # Lazy init — create runner if not done in create_session
            runner = await self._create_runner(session)
            self._runners[session_id] = runner

        # Pre-create the event queue BEFORE scheduling the task so that
        # stream_events() always finds the same queue object even if the
        # background task completes (and would otherwise call close_queue)
        # before the consumer calls get_queue for the first time.
        self._emitter.get_queue(run_id)

        # Schedule the turn execution as a background task
        task = asyncio.get_running_loop().create_task(
            self._execute_turn(
                session=session,
                run_id=run_id,
                turn_id=turn_id,
                user_input=user_input,
                runner=runner,
            ),
            name=f"run-{run_id[:8]}",
        )

        active = _ActiveRun(
            run_id=run_id,
            session_id=session_id,
            task=task,
            runner=runner,
        )
        async with self._active_lock:
            self._active[session_id] = active

        return run_id

    async def _execute_turn(
        self,
        session: Session,
        run_id: str,
        turn_id: str,
        user_input: str,
        runner: IFrameworkRunner,
    ) -> None:
        """Background task: drive the full turn FSM."""
        session_id = session.config.session_id
        self._emitter.get_queue(run_id)

        async def _transition(new_state: RunState, reason: str | None = None) -> None:
            run = await self._runs.get(run_id)
            await self._runs.transition(run_id, new_state)
            self._emitter.emit(
                RunStateEvent(
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    from_state=run.state,
                    to_state=new_state,
                    reason=reason,
                )
            )

        # Mutable box so exception branches can set the terminal reason
        # before the finally block reads it.
        _terminal: list[tuple[str, str]] = [("completed", "")]

        try:
            # 1. PENDING → CONTEXT_ASSEMBLING
            await _transition(RunState.CONTEXT_ASSEMBLING)
            await self._sessions.touch(session_id)

            # 2. Assemble context
            context_obj = await self._assembler.assemble(session, user_input, run_id)

            # 3. CONTEXT_ASSEMBLING → EXECUTING
            await _transition(RunState.EXECUTING)

            # 4. Delegate to framework runner
            event_queue = self._emitter.get_queue(run_id)
            await runner.run_turn(user_input, context_obj, event_queue)

            # 5. EXECUTING → COMPLETED
            await _transition(RunState.COMPLETED)
            await self._runs.increment_turn(run_id)

        except asyncio.CancelledError:
            _terminal[0] = ("cancelled", "")
            run = await self._runs.get(run_id)
            if run.state not in (RunState.COMPLETED, RunState.FAILED):
                try:
                    await self._runs.transition(run_id, RunState.CANCELLED)
                    self._emitter.emit(
                        RunStateEvent(
                            session_id=session_id,
                            run_id=run_id,
                            turn_id=turn_id,
                            from_state=run.state,
                            to_state=RunState.CANCELLED,
                            reason="cancelled",
                        )
                    )
                except Exception as _inner:
                    runtime_logger.debug("run_cancel_state_transition_failed", run_id=run_id, error=str(_inner))
            raise

        except CitnegaRuntimeError as exc:
            _terminal[0] = (exc.error_code or "failed", str(exc))
            runtime_logger.error(
                "run_failed",
                run_id=run_id,
                error=str(exc),
                error_code=exc.error_code,
            )
            run = await self._runs.get(run_id)
            if run.state not in (RunState.COMPLETED, RunState.CANCELLED):
                try:
                    await self._runs.transition(run_id, RunState.FAILED, error=str(exc))
                    self._emitter.emit(
                        RunStateEvent(
                            session_id=session_id,
                            run_id=run_id,
                            turn_id=turn_id,
                            from_state=run.state,
                            to_state=RunState.FAILED,
                            reason=str(exc),
                        )
                    )
                except Exception as _inner:
                    runtime_logger.debug("run_error_state_transition_failed", run_id=run_id, error=str(_inner))

        except Exception as exc:
            _terminal[0] = ("failed", str(exc))
            runtime_logger.exception(
                "run_unhandled_error",
                run_id=run_id,
                error=str(exc),
            )
            run = await self._runs.get(run_id)
            if run.state not in (RunState.COMPLETED, RunState.CANCELLED):
                try:
                    await self._runs.transition(run_id, RunState.FAILED, error=str(exc))
                    self._emitter.emit(
                        RunStateEvent(
                            session_id=session_id,
                            run_id=run_id,
                            turn_id=turn_id,
                            from_state=run.state,
                            to_state=RunState.FAILED,
                            reason=str(exc),
                        )
                    )
                except Exception as _inner:
                    runtime_logger.debug("run_unhandled_state_transition_failed", run_id=run_id, error=str(_inner))

        finally:
            # Emit terminal reason regardless of outcome.
            run = await self._runs.get(run_id)
            reason_code, reason_details = _terminal[0]
            self._emitter.emit(
                RunTerminalReasonEvent(
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    reason=reason_code,
                    details=reason_details,
                )
            )

            # Keep the run marked active until session state persistence is done.
            # This prevents shutdown() from missing an in-flight cleanup task.
            try:
                await self._sessions.set_idle(session_id)
            except Exception as exc:
                runtime_logger.warning(
                    "session_set_idle_failed",
                    session_id=session_id,
                    run_id=run_id,
                    error=str(exc),
                )
            finally:
                async with self._active_lock:
                    self._active.pop(session_id, None)

            # Emit completion sentinel only after cleanup is persisted and
            # the run is removed from active bookkeeping. This guarantees
            # callers can safely start the next run after observing RunCompleteEvent.
            self._emitter.emit(
                RunCompleteEvent(
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    final_state=run.state,
                )
            )
            # Note: close_queue is NOT called here — the consumer (stream_events)
            # owns cleanup once it has read RunCompleteEvent.

    # ------------------------------------------------------------------
    # Control operations
    # ------------------------------------------------------------------

    async def pause_run(self, run_id: str) -> None:
        active = await self._find_active_by_run(run_id)
        await self._runs.transition(run_id, RunState.PAUSED)
        await active.runner.pause(run_id)

    async def resume_run(self, run_id: str) -> None:
        active = await self._find_active_by_run(run_id)
        await self._runs.transition(run_id, RunState.EXECUTING)
        await active.runner.resume(run_id)

    async def cancel_run(self, run_id: str) -> None:
        active = await self._find_active_by_run(run_id)
        active.cancelled = True
        active.task.cancel()
        # Wait briefly for cancellation to propagate
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(active.task), timeout=5.0)

    async def _find_active_by_run(self, run_id: str) -> _ActiveRun:
        async with self._active_lock:
            for active in self._active.values():
                if active.run_id == run_id:
                    return active
        raise RunNotFoundError(f"No active run {run_id!r}.")

    # ------------------------------------------------------------------
    # State snapshot
    # ------------------------------------------------------------------

    async def get_state_snapshot(self, session_id: str) -> StateSnapshot:
        await self._sessions.get(session_id)
        async with self._active_lock:
            active = self._active.get(session_id)

        if active:
            run = await self._runs.get(active.run_id)
            runner_snapshot = await active.runner.get_state_snapshot()
            return StateSnapshot(
                session_id=session_id,
                current_run_id=active.run_id,
                active_callable=runner_snapshot.active_callable,
                run_state=run.state,
                context_token_count=runner_snapshot.context_token_count,
                checkpoint_available=runner_snapshot.checkpoint_available,
                framework_name=self._adapter.framework_name,
                captured_at=datetime.now(tz=UTC),
            )

        return StateSnapshot(
            session_id=session_id,
            current_run_id=None,
            active_callable=None,
            run_state=RunState.PENDING,
            context_token_count=0,
            checkpoint_available=False,
            framework_name=self._adapter.framework_name,
            captured_at=datetime.now(tz=UTC),
        )

    # ------------------------------------------------------------------
    # Event queue access
    # ------------------------------------------------------------------

    def get_event_queue(self, run_id: str) -> asyncio.Queue[CanonicalEvent]:
        return self._emitter.get_queue(run_id)

    # ------------------------------------------------------------------
    # Callable registry
    # ------------------------------------------------------------------

    def register_callable(self, callable: IInvocable) -> None:
        self._registry.register(callable.name, callable)

    def list_callables(self) -> list[CallableMetadata]:
        return [c.get_metadata() for c in self._registry.list_all()]

    # ------------------------------------------------------------------
    # Public accessors (used by ApplicationService to avoid private access)
    # ------------------------------------------------------------------

    async def get_session(self, session_id: str) -> Session:
        """Return *session_id*, raising SessionNotFoundError if absent."""
        return await self._sessions.get(session_id)

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        """Return all sessions, capped to *limit*."""
        all_sessions = await self._sessions.list_all()
        return all_sessions[:limit]

    async def delete_session(self, session_id: str) -> None:
        await self._sessions.delete(session_id)

    async def save_session(self, session: Session) -> None:
        """Persist a modified session record."""
        await self._sessions.save(session)

    async def get_run_summary(self, run_id: str) -> RunSummary | None:
        """Return a run summary, or None if not found."""
        try:
            return await self._runs.get(run_id)
        except RunNotFoundError:
            return None

    async def list_runs_for_session(self, session_id: str, limit: int = 50) -> list[RunSummary]:
        return await self._runs.list_for_session(session_id, limit=limit)

    @property
    def adapter(self) -> IFrameworkAdapter:
        """The active framework adapter."""
        return self._adapter

    @property
    def callable_registry(self) -> BaseRegistry[IInvocable]:
        """The unified callable registry."""
        return self._registry

    @property
    def capability_registry(self) -> CapabilityRegistry | None:
        """The capability registry (may be None if not built at bootstrap)."""
        return self._capability_registry

    def get_runner(self, session_id: str) -> IFrameworkRunner | None:
        return self._runners.get(session_id)

    async def ensure_runner(self, session_id: str) -> IFrameworkRunner | None:
        runner = self._runners.get(session_id)
        if runner is not None:
            return runner
        session = await self._sessions.get(session_id)
        runner = await self._create_runner(session)
        self._runners[session_id] = runner
        return runner

    async def refresh_runners(self) -> dict[str, list[str]]:
        refreshed: list[str] = []
        skipped: list[str] = []
        for session_id in list(self._runners):
            async with self._active_lock:
                is_active = session_id in self._active
            if is_active:
                skipped.append(session_id)
                continue
            session = await self._sessions.get(session_id)
            self._runners[session_id] = await self._create_runner(session)
            refreshed.append(session_id)
        return {"refreshed": refreshed, "skipped": skipped}

    async def _create_runner(self, session: Session) -> IFrameworkRunner:
        return await self._adapter.create_runner(
            session,
            self._registry.list_all(),
            self._model_gateway,
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Cancel all active runs and wait for them to finish."""
        runtime_logger.info("runtime_shutdown_start")
        async with self._active_lock:
            active_list = list(self._active.values())

        for active in active_list:
            if not active.task.done():
                active.task.cancel()

        if active_list:
            await asyncio.gather(
                *(a.task for a in active_list),
                return_exceptions=True,
            )

        await self._adapter.shutdown()
        runtime_logger.info("runtime_shutdown_complete")
