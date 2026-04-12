"""IRuntime — core runtime interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.types import CallableMetadata
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models import Session, SessionConfig, StateSnapshot


class IRuntime(ABC):
    """
    Core runtime: session lifecycle, run execution, and callable registration.

    The ApplicationService delegates all domain work to IRuntime.
    """

    @abstractmethod
    async def create_session(self, config: SessionConfig) -> Session: ...

    @abstractmethod
    async def run_turn(self, session_id: str, user_input: str) -> str:
        """Initiates a turn. Returns the run_id immediately (non-blocking start)."""
        ...

    @abstractmethod
    def get_event_queue(self, run_id: str) -> asyncio.Queue[CanonicalEvent]: ...

    @abstractmethod
    async def pause_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def resume_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def cancel_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def get_state_snapshot(self, session_id: str) -> StateSnapshot: ...

    @abstractmethod
    def register_callable(self, callable: IInvocable) -> None: ...

    @abstractmethod
    def list_callables(self) -> list[CallableMetadata]: ...

    @abstractmethod
    async def shutdown(self) -> None: ...
