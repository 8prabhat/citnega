"""
StubFrameworkAdapter — minimal IFrameworkAdapter for testing Phase 2.

The stub:
  - Accepts any callables at create_runner() time.
  - Runs each turn synchronously in the event loop: emits a RunStateEvent
    and returns.
  - Records turn inputs in ``turns_run`` for assertions.
  - Supports pause/resume/cancel as no-ops (state tracked in memory).
  - Provides a deterministic StateSnapshot.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.interfaces.adapter import (
    AdapterConfig,
    ICallableFactory,
    IFrameworkAdapter,
    IFrameworkRunner,
)
from citnega.packages.protocol.models.checkpoints import CheckpointMeta
from citnega.packages.protocol.models.runs import RunState, StateSnapshot

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session


class StubCallableFactory(ICallableFactory):
    """No-op factory — returns the callable as-is."""

    def create_tool(self, callable: IInvocable) -> Any:
        return callable

    def create_specialist(self, callable: IStreamable) -> Any:
        return callable

    def create_core_agent(self, callable: IStreamable) -> Any:
        return callable

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        from citnega.packages.protocol.events import GenericFrameworkEvent

        return GenericFrameworkEvent(
            session_id="",
            run_id="",
            framework_name="stub",
            framework_event_type=type(framework_event).__name__,
            payload={"raw": str(framework_event)},
        )


class StubFrameworkRunner(IFrameworkRunner):
    """
    Minimal runner for integration tests.

    Behaviour per turn:
      1. Records the turn in ``turns_run``.
      2. Optionally raises the first item in ``errors_to_raise``.
      3. Optionally sleeps for ``sleep_seconds`` (simulates long execution).
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self.turns_run: list[dict[str, object]] = []
        self.errors_to_raise: list[Exception] = []
        self.sleep_seconds: float = 0.0
        self._paused = False
        self._cancelled = False

    async def run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        if self._cancelled:
            raise asyncio.CancelledError("run was cancelled")

        if self.errors_to_raise:
            raise self.errors_to_raise.pop(0)

        if self.sleep_seconds > 0:
            await asyncio.sleep(self.sleep_seconds)

        self.turns_run.append(
            {
                "user_input": user_input,
                "run_id": context.run_id,
                "session_id": context.session_id,
            }
        )

        # Emit a stub response so the TUI has tokens to display
        import uuid as _uuid

        from citnega.packages.protocol.events.streaming import TokenEvent

        reply = f"[stub] You said: {user_input}"
        for word in reply.split():
            await event_queue.put(
                TokenEvent(
                    session_id=context.session_id,
                    run_id=context.run_id,
                    turn_id=str(_uuid.uuid4()),
                    token=word + " ",
                )
            )
            await asyncio.sleep(0.02)  # simulate streaming delay

        return context.run_id

    async def pause(self, run_id: str) -> None:
        self._paused = True

    async def resume(self, run_id: str) -> None:
        self._paused = False

    async def cancel(self, run_id: str) -> None:
        self._cancelled = True

    async def get_state_snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            session_id=self._session.config.session_id,
            current_run_id=None,
            active_callable=None,
            run_state=RunState.EXECUTING,
            context_token_count=0,
            checkpoint_available=False,
            framework_name="stub",
            captured_at=datetime.now(tz=UTC),
        )

    async def save_checkpoint(self, run_id: str) -> CheckpointMeta:
        import json as _json
        import tempfile as _tf
        import uuid as _uuid

        state = {"run_id": run_id, "session_id": self._session.config.session_id}
        payload = _json.dumps(state).encode()
        # Write to a real temp file so size_bytes > 0
        with _tf.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(payload)
            fpath = f.name
        return CheckpointMeta(
            checkpoint_id=str(_uuid.uuid4()),
            session_id=self._session.config.session_id,
            run_id=run_id,
            created_at=datetime.now(tz=UTC),
            framework_name="stub",
            file_path=fpath,
            size_bytes=len(payload),
            state_summary=_json.dumps(state),
        )

    async def restore_checkpoint(self, checkpoint_id: str) -> None:
        pass  # no-op


class StubFrameworkAdapter(IFrameworkAdapter):
    """
    Stub adapter that creates StubFrameworkRunner instances.

    Usable in any test that needs an IFrameworkAdapter without real
    framework dependencies.
    """

    def __init__(self) -> None:
        self._config: AdapterConfig | None = None
        self._factory = StubCallableFactory()
        self.runner_created_count = 0

    @property
    def framework_name(self) -> str:
        return "stub"

    async def initialize(self, config: AdapterConfig) -> None:
        self._config = config

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> StubFrameworkRunner:
        self.runner_created_count += 1
        return StubFrameworkRunner(session)

    async def shutdown(self) -> None:
        pass

    @property
    def callable_factory(self) -> StubCallableFactory:
        return self._factory
