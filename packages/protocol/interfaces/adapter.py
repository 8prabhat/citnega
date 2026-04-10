"""Framework adapter interfaces."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
from citnega.packages.protocol.events import CanonicalEvent
from citnega.packages.protocol.models import Session, StateSnapshot
from citnega.packages.protocol.models.checkpoints import CheckpointMeta


class AdapterConfig(BaseModel):
    framework_name:      str
    default_model_id:    str
    framework_specific:  dict[str, Any] = Field(default_factory=dict)


class IFrameworkAdapter(ABC):
    """
    Port interface that all framework adapters (ADK, LangGraph, CrewAI) implement.

    Only ``packages/adapters/<fw>/`` may import the corresponding framework SDK.
    """

    @property
    @abstractmethod
    def framework_name(self) -> str: ...

    @abstractmethod
    async def initialize(self, config: AdapterConfig) -> None: ...

    @abstractmethod
    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: "IModelGateway",  # type: ignore[name-defined]  # noqa: F821
    ) -> "IFrameworkRunner": ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @property
    @abstractmethod
    def callable_factory(self) -> "ICallableFactory": ...


class IFrameworkRunner(ABC):
    """Session-scoped execution handle returned by IFrameworkAdapter.create_runner()."""

    @abstractmethod
    async def run_turn(
        self,
        user_input: str,
        context: "ContextObject",  # type: ignore[name-defined]  # noqa: F821
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        """Execute one turn. Returns the run_id."""
        ...

    @abstractmethod
    async def pause(self, run_id: str) -> None: ...

    @abstractmethod
    async def resume(self, run_id: str) -> None: ...

    @abstractmethod
    async def cancel(self, run_id: str) -> None: ...

    @abstractmethod
    async def get_state_snapshot(self) -> StateSnapshot: ...

    @abstractmethod
    async def save_checkpoint(self, run_id: str) -> CheckpointMeta: ...

    @abstractmethod
    async def restore_checkpoint(self, checkpoint_id: str) -> None: ...


class ICallableFactory(ABC):
    """
    Converts Citnega-native callables to the framework's native representation.

    One implementation per framework adapter.
    """

    @abstractmethod
    def create_tool(self, callable: IInvocable) -> Any: ...

    @abstractmethod
    def create_specialist(self, callable: IStreamable) -> Any: ...

    @abstractmethod
    def create_core_agent(self, callable: IStreamable) -> Any: ...

    @abstractmethod
    def translate_event(self, framework_event: Any) -> CanonicalEvent | None: ...
