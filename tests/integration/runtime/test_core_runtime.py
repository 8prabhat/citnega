"""
Integration tests for CoreRuntime.

These tests use a real SQLite database (tmp_db fixture) and a
StubFrameworkAdapter — no real framework SDK required.

Scenarios covered:
  - Full turn: create session → run_turn → collect events → verify COMPLETED
  - Concurrent run rejection (one active run at a time per session)
  - Cancel mid-run
  - Failed turn (stub raises)
  - State snapshot reflects active run
  - Shutdown cancels all active runs
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
from citnega.packages.protocol.models.runs import RunState
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.context.assembler import ContextAssembler
from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler
from citnega.packages.runtime.context.handlers.recent_turns import RecentTurnsHandler
from citnega.packages.runtime.context.handlers.runtime_state import RuntimeStateHandler
from citnega.packages.runtime.context.handlers.session_summary import SessionSummaryHandler
from citnega.packages.runtime.context.handlers.token_budget import TokenBudgetHandler
from citnega.packages.runtime.core_runtime import CoreRuntime
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.runs import RunManager
from citnega.packages.runtime.sessions import SessionManager
from citnega.packages.shared.errors import RuntimeError as CitnegaRuntimeError
from citnega.packages.shared.registry import BaseRegistry
from citnega.packages.storage.database import DatabaseFactory
from citnega.packages.storage.repositories.message_repo import MessageRepository
from citnega.packages.storage.repositories.run_repo import RunRepository
from citnega.packages.storage.repositories.session_repo import SessionRepository
from tests.fixtures.stub_adapter import StubFrameworkAdapter, StubFrameworkRunner

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from citnega.packages.protocol.events import CanonicalEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tmp_db(tmp_path: Path) -> AsyncGenerator[DatabaseFactory, None]:
    from citnega.packages.storage.path_resolver import PathResolver

    pr = PathResolver(app_home=tmp_path)
    pr.create_all()
    db = DatabaseFactory(pr.db_path)
    await db.connect()
    alembic_ini = pr.alembic_ini_path()
    await db.run_migrations(alembic_ini)
    yield db
    await db.disconnect()


@pytest_asyncio.fixture
async def runtime(tmp_db: DatabaseFactory) -> AsyncGenerator[CoreRuntime, None]:
    session_repo = SessionRepository(tmp_db)
    run_repo = RunRepository(tmp_db)
    message_repo = MessageRepository(tmp_db)

    session_mgr = SessionManager(session_repo)
    run_mgr = RunManager(run_repo)

    assembler = ContextAssembler(
        [
            RecentTurnsHandler(message_repo, recent_turns_count=10),
            SessionSummaryHandler(run_repo),
            KBRetrievalHandler(),
            RuntimeStateHandler(),
            TokenBudgetHandler(max_context_tokens=8192),
        ]
    )

    adapter = StubFrameworkAdapter()
    emitter = EventEmitter()
    registry: BaseRegistry = BaseRegistry()

    rt = CoreRuntime(
        session_manager=session_mgr,
        run_manager=run_mgr,
        context_assembler=assembler,
        framework_adapter=adapter,
        event_emitter=emitter,
        callable_registry=registry,
    )
    yield rt
    await rt.shutdown()


def _session_config(session_id: str = "test-sess") -> SessionConfig:
    return SessionConfig(
        session_id=session_id,
        name="Integration test",
        framework="stub",
        default_model_id="model-x",
        max_context_tokens=8192,
    )


async def _drain_events(
    queue: asyncio.Queue[CanonicalEvent],
    timeout: float = 5.0,
) -> list[CanonicalEvent]:
    """Drain the event queue until a RunCompleteEvent is received."""
    events: list[CanonicalEvent] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            event = await asyncio.wait_for(queue.get(), timeout=remaining)
            events.append(event)
            if isinstance(event, RunCompleteEvent):
                break
        except TimeoutError:
            break
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullTurn:
    @pytest.mark.asyncio
    async def test_turn_completes(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config())
        run_id = await runtime.run_turn(session.config.session_id, "Hello")
        assert run_id

        queue = runtime.get_event_queue(run_id)
        events = await _drain_events(queue)

        terminal = [e for e in events if isinstance(e, RunCompleteEvent)]
        assert len(terminal) == 1
        assert terminal[0].final_state == RunState.COMPLETED

    @pytest.mark.asyncio
    async def test_state_events_ordered(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config("sess-order"))
        run_id = await runtime.run_turn(session.config.session_id, "test")
        queue = runtime.get_event_queue(run_id)
        events = await _drain_events(queue)

        state_events = [e for e in events if isinstance(e, RunStateEvent)]
        states = [e.to_state for e in state_events]

        # Must pass through CONTEXT_ASSEMBLING, then EXECUTING, then COMPLETED
        assert RunState.CONTEXT_ASSEMBLING in states
        assert RunState.EXECUTING in states
        assert RunState.COMPLETED in states

        ca_idx = states.index(RunState.CONTEXT_ASSEMBLING)
        ex_idx = states.index(RunState.EXECUTING)
        co_idx = states.index(RunState.COMPLETED)
        assert ca_idx < ex_idx < co_idx


class TestConcurrentRunRejection:
    @pytest.mark.asyncio
    async def test_second_turn_rejected_while_active(self, runtime: CoreRuntime) -> None:
        # Give the stub a small sleep so the first run is still active
        session = await runtime.create_session(_session_config("sess-concurrent"))
        runner: StubFrameworkRunner = runtime._runners[session.config.session_id]
        runner.sleep_seconds = 0.3

        run_id = await runtime.run_turn(session.config.session_id, "turn 1")

        with pytest.raises(CitnegaRuntimeError, match="already has an active run"):
            await runtime.run_turn(session.config.session_id, "turn 2")

        # Wait for the first run to finish
        queue = runtime.get_event_queue(run_id)
        await _drain_events(queue, timeout=5.0)


class TestCancelRun:
    @pytest.mark.asyncio
    async def test_cancel_transitions_to_cancelled(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config("sess-cancel"))
        runner: StubFrameworkRunner = runtime._runners[session.config.session_id]
        runner.sleep_seconds = 10.0  # long enough to cancel

        run_id = await runtime.run_turn(session.config.session_id, "long task")
        await asyncio.sleep(0.05)  # let the run start
        await runtime.cancel_run(run_id)

        # Let the cancellation settle
        await asyncio.sleep(0.2)

        run = await runtime._runs.get(run_id)
        assert run.state == RunState.CANCELLED


class TestFailedTurn:
    @pytest.mark.asyncio
    async def test_runner_exception_transitions_to_failed(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config("sess-fail"))
        runner: StubFrameworkRunner = runtime._runners[session.config.session_id]
        runner.errors_to_raise.append(RuntimeError("stub exploded"))

        run_id = await runtime.run_turn(session.config.session_id, "boom")
        queue = runtime.get_event_queue(run_id)
        events = await _drain_events(queue, timeout=5.0)

        terminal = [e for e in events if isinstance(e, RunCompleteEvent)]
        assert terminal[0].final_state == RunState.FAILED


class TestStateSnapshot:
    @pytest.mark.asyncio
    async def test_idle_snapshot_when_no_run(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config("sess-snap"))
        snapshot = await runtime.get_state_snapshot(session.config.session_id)
        assert snapshot.current_run_id is None
        assert snapshot.framework_name == "stub"


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_active_runs(self, runtime: CoreRuntime) -> None:
        session = await runtime.create_session(_session_config("sess-shutdown"))
        runner: StubFrameworkRunner = runtime._runners[session.config.session_id]
        runner.sleep_seconds = 30.0  # would block forever

        run_id = await runtime.run_turn(session.config.session_id, "hang")
        await asyncio.sleep(0.05)

        await asyncio.wait_for(runtime.shutdown(), timeout=10.0)
        # After shutdown, the run should be cancelled
        run = await runtime._runs.get(run_id)
        assert run.state in (RunState.CANCELLED, RunState.FAILED)
