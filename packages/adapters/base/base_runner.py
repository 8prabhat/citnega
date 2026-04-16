"""
BaseFrameworkRunner — partial implementation of IFrameworkRunner.

Concrete runners extend this and implement:
  - ``_do_run_turn(user_input, context, event_queue)`` → str (run_id)
  - ``_do_pause(run_id)``
  - ``_do_resume(run_id)``
  - ``_do_cancel(run_id)``
  - ``_do_get_state_snapshot()`` → StateSnapshot
  - ``_do_save_checkpoint(run_id)`` → dict (framework_state)

Shared behaviour (provided here):
  - Cancellation via CancellationToken.
  - Checkpoint save/restore using CheckpointSerializer.
  - Correlation field propagation.
  - Structured logging.
"""

from __future__ import annotations

from abc import abstractmethod
import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.adapter import IFrameworkRunner
from citnega.packages.protocol.models.runs import RunState, StateSnapshot

if TYPE_CHECKING:
    from citnega.packages.adapters.base.cancellation import CancellationToken
    from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.checkpoints import CheckpointMeta
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session


class BaseFrameworkRunner(IFrameworkRunner):
    """
    Shared state and helpers for all framework runners.

    The ``run_turn`` method wraps ``_do_run_turn`` with cancellation
    checks and structured logging.
    """

    def __init__(
        self,
        session: Session,
        cancellation_token: CancellationToken,
        checkpoint_serializer: CheckpointSerializer,
    ) -> None:
        self._session = session
        self._token = cancellation_token
        self._serializer = checkpoint_serializer
        self._current_run_id: str | None = None
        self._paused = False
        self._active_callable: str | None = None
        self._context_token_count = 0

    # ------------------------------------------------------------------
    # IFrameworkRunner contract
    # ------------------------------------------------------------------

    async def run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        if self._token.is_cancelled():
            raise asyncio.CancelledError("runner already cancelled")

        self._current_run_id = context.run_id
        self._context_token_count = context.total_tokens

        runtime_logger.debug(
            "runner_turn_start",
            session_id=self._session.config.session_id,
            run_id=context.run_id,
            input_length=len(user_input),
        )

        run_id = await self._do_run_turn(user_input, context, event_queue)

        runtime_logger.debug(
            "runner_turn_end",
            session_id=self._session.config.session_id,
            run_id=context.run_id,
        )
        return run_id

    async def pause(self, run_id: str) -> None:
        self._paused = True
        await self._do_pause(run_id)

    async def resume(self, run_id: str) -> None:
        self._paused = False
        await self._do_resume(run_id)

    async def cancel(self, run_id: str) -> None:
        self._token.cancel()
        await self._do_cancel(run_id)

    async def get_state_snapshot(self) -> StateSnapshot:
        state = await self._do_get_state_snapshot()
        return StateSnapshot(
            session_id=self._session.config.session_id,
            current_run_id=self._current_run_id,
            active_callable=self._active_callable,
            run_state=state,
            context_token_count=self._context_token_count,
            checkpoint_available=False,
            framework_name=self._session.config.framework,
            captured_at=datetime.now(tz=UTC),
        )

    async def save_checkpoint(self, run_id: str) -> CheckpointMeta:
        framework_state = await self._do_save_checkpoint(run_id)
        return self._serializer.save(
            session_id=self._session.config.session_id,
            run_id=run_id,
            framework_state=framework_state,
        )

    async def restore_checkpoint(self, checkpoint_id: str) -> None:
        # Locate the checkpoint file via the serializer's directory
        matches = list(self._serializer._dir.glob(f"{checkpoint_id}.json.gz"))
        if not matches:
            from citnega.packages.shared.errors import StorageError

            raise StorageError(f"Checkpoint {checkpoint_id!r} not found.")
        blob = self._serializer.load(str(matches[0]))
        fw_state = blob.get("framework_state", {})
        if not isinstance(fw_state, dict):
            from citnega.packages.shared.errors import StorageError

            raise StorageError(f"Invalid framework_state in checkpoint {checkpoint_id!r}")
        await self._do_restore_checkpoint(fw_state)

    # ------------------------------------------------------------------
    # Abstract hooks (implement in concrete runner)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str: ...

    @abstractmethod
    async def _do_pause(self, run_id: str) -> None: ...

    @abstractmethod
    async def _do_resume(self, run_id: str) -> None: ...

    @abstractmethod
    async def _do_cancel(self, run_id: str) -> None: ...

    @abstractmethod
    async def _do_get_state_snapshot(self) -> RunState: ...

    @abstractmethod
    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]: ...

    async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
        """Optional: restore framework-specific state. Default: no-op."""
