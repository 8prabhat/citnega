"""IPolicyEnforcer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter

_T = TypeVar("_T")


class IPolicyEnforcer(ABC):
    """
    Enforces execution policies before and after any IInvocable runs.

    Pre-execution  : enforce() — depth, path, network, approval.
    Execution wrap : run_with_timeout() — wraps _execute coroutine.
    Post-execution : check_output_size() — verifies output byte count.

    Raises a CallablePolicyError subclass on any violation.
    Returns None / passes through result when checks pass.
    """

    @abstractmethod
    async def enforce(
        self,
        callable: IInvocable,
        input: BaseModel,
        context: CallContext,
    ) -> None: ...

    @staticmethod
    @abstractmethod
    async def run_with_timeout(
        callable: IInvocable,
        coro: Awaitable[_T],
        context: CallContext,
        emitter: IEventEmitter,
    ) -> _T:
        """Wrap *coro* with the callable's policy timeout_seconds."""
        ...

    @staticmethod
    @abstractmethod
    async def check_output_size(
        callable: IInvocable,
        output_bytes: int,
        context: CallContext,
        emitter: IEventEmitter,
    ) -> None:
        """Raise OutputTooLargeError if output_bytes > policy.max_output_bytes."""
        ...
