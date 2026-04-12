"""IEventEmitter and ITracer interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.results import InvokeResult
    from citnega.packages.protocol.events import CanonicalEvent


class IEventEmitter(ABC):
    """
    Writes canonical events into per-run asyncio queues.

    ``emit()`` is synchronous and non-blocking (put_nowait semantics).
    Backpressure is applied by the bounded queue (maxsize=256).
    """

    @abstractmethod
    def emit(self, event: CanonicalEvent) -> None: ...

    @abstractmethod
    def get_queue(self, run_id: str) -> asyncio.Queue[CanonicalEvent]: ...

    @abstractmethod
    def close_queue(self, run_id: str) -> None: ...


class ITracer(ABC):
    """Records callable invocations to the callable_invocations table."""

    @abstractmethod
    def record(
        self,
        callable: IInvocable,
        input: BaseModel,
        result: InvokeResult,
        context: CallContext,
    ) -> None: ...
