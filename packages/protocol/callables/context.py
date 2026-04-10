"""CallContext — execution context passed to every callable invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.model_gateway import IModelGateway  # noqa: F401 (used in docstrings/comments)


class CallContext(BaseModel):
    """
    Immutable execution context injected into every callable.

    Contains session config, routing metadata, and references to
    infrastructure (model gateway) that agents — but not plain tools —
    may use.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id:      str
    run_id:          str
    turn_id:         str
    depth:           int  = 0            # invocation depth within a turn
    parent_callable: str | None = None
    session_config:  SessionConfig
    model_gateway:   Any = None   # IModelGateway | None — injected for agents only
    deadline:        float | None = None              # monotonic clock deadline
    metadata:        dict[str, Any] = Field(default_factory=dict)

    # Internal cleanup handlers registered by tools that spawn subprocesses
    _cleanup_handlers: list[Callable[[], None]] = []

    def register_cleanup(self, fn: Callable[[], None]) -> None:
        """Register a cleanup function called on timeout/cancel."""
        self._cleanup_handlers.append(fn)

    def run_cleanups(self) -> None:
        """Execute all registered cleanup handlers (best-effort)."""
        for fn in self._cleanup_handlers:
            try:
                fn()
            except Exception:
                pass

    def child(
        self,
        callable_name: str,
        callable_type: CallableType,  # noqa: ARG002
    ) -> "CallContext":
        """Create a child context with incremented depth."""
        return CallContext(
            session_id=self.session_id,
            run_id=self.run_id,
            turn_id=self.turn_id,
            depth=self.depth + 1,
            parent_callable=callable_name,
            session_config=self.session_config,
            model_gateway=self.model_gateway,
            deadline=self.deadline,
            metadata=dict(self.metadata),
        )


