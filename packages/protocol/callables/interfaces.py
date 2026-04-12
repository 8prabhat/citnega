"""
IInvocable → IStreamable → IOrchestrable callable interface hierarchy.

ISP-segregated so that:
  - IInvocable  : minimum contract (all callables satisfy this)
  - IStreamable : adds streaming (tools + specialists)
  - IOrchestrable: adds sub-callable management (core agents only)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.results import InvokeResult, StreamChunk
    from citnega.packages.protocol.callables.types import (
        CallableMetadata,
        CallablePolicy,
        CallableType,
    )
    from citnega.packages.protocol.interfaces.routing import IRoutingPolicy


class IInvocable(ABC):
    """
    Minimum callable contract.

    Every tool, specialist, and core agent implements this interface.
    ``invoke()`` must *never* raise — all errors are captured inside
    ``InvokeResult.error``.
    """

    name: str
    description: str
    callable_type: CallableType
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    policy: CallablePolicy

    @abstractmethod
    async def invoke(self, input: BaseModel, context: CallContext) -> InvokeResult: ...

    @abstractmethod
    def get_metadata(self) -> CallableMetadata: ...


class IStreamable(IInvocable, ABC):
    """
    IInvocable + streaming support.

    ``stream_invoke()`` on non-streaming callables must yield at least one
    RESULT chunk followed by a TERMINAL chunk. It must never block indefinitely.
    """

    @abstractmethod
    async def stream_invoke(
        self,
        input: BaseModel,
        context: CallContext,
    ) -> AsyncIterator[StreamChunk]: ...


class IOrchestrable(IStreamable, ABC):
    """
    IStreamable + sub-callable management.

    Only core agents implement this interface.
    """

    @abstractmethod
    def register_sub_callable(self, callable: IInvocable) -> None: ...

    @abstractmethod
    def list_sub_callables(self) -> list[IInvocable]: ...

    @abstractmethod
    def set_routing_policy(self, policy: IRoutingPolicy) -> None: ...
