"""Framework adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import asyncio

    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.interfaces.model_gateway import IModelGateway
    from citnega.packages.protocol.models import Session, StateSnapshot
    from citnega.packages.protocol.models.checkpoints import CheckpointMeta
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.runner import ConversationStats, ThinkingConfig


class AdapterConfig(BaseModel):
    framework_name: str
    default_model_id: str
    framework_specific: dict[str, Any] = Field(default_factory=dict)


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
        model_gateway: IModelGateway,
    ) -> IFrameworkRunner: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    @property
    @abstractmethod
    def callable_factory(self) -> ICallableFactory: ...

    def get_runner(self, session_id: str) -> IFrameworkRunner | None:
        """Return the runner for *session_id*, or None if not created yet."""
        return None

    async def set_session_model(self, session_id: str, model_id: str) -> None:
        """Switch the active model for an existing session. No-op by default."""


class IFrameworkRunner(ABC):
    """Session-scoped execution handle returned by IFrameworkAdapter.create_runner()."""

    @abstractmethod
    async def run_turn(
        self,
        user_input: str,
        context: ContextObject,
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

    # ── Typed accessors (non-abstract — default impls for adapters that ──
    # ── don't manage conversation state internally)                      ──

    def get_active_model_id(self) -> str | None:
        """Return the active model ID for this runner's session."""
        return None

    def get_mode(self) -> str:
        """Return the session mode name (``"chat"`` | ``"plan"`` | ``"explore"``)."""
        return "chat"

    def set_plan_phase(self, phase: str | None) -> None:
        """Set the plan phase (``"draft"`` | ``"execute"`` | None)."""

    async def set_mode(self, mode_name: str) -> None:
        """Switch the session mode."""

    async def set_model(self, model_id: str) -> None:
        """Switch the active model for this runner's session."""

    async def set_thinking(self, value: bool | None) -> None:
        """Override thinking for the session."""

    def get_thinking(self) -> bool | None:
        """Return the thinking override (``None`` = auto)."""
        return None

    def get_conversation_stats(self) -> ConversationStats:
        """Return conversation statistics for the session."""
        from citnega.packages.protocol.models.runner import ConversationStats as _CS

        return _CS()

    def get_messages(self) -> list[dict[str, Any]]:
        """Return the conversation message list."""
        return []

    def get_tool_history(self) -> list[dict[str, Any]]:
        """Return tool call history."""
        return []

    async def add_tool_call(
        self,
        name: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        callable_type: str = "tool",
    ) -> None:
        """Record a completed tool/agent call."""

    async def compact(self, summary: str, *, keep_recent: int = 10) -> int:
        """Compact conversation. Returns the number of messages archived."""
        return 0


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
