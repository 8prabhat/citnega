"""RuntimeStateHandler — injects a snapshot of the current run state."""

from __future__ import annotations

from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.protocol.models.runs import StateSnapshot
from citnega.packages.protocol.models.sessions import Session


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class RuntimeStateHandler(IContextHandler):
    """
    Injects the current run's StateSnapshot so the model knows:
      - which run is active
      - the current run state
      - whether a checkpoint is available
      - which framework is in use

    The snapshot is provided at assembly time via ``set_snapshot()``.
    If no snapshot has been set (e.g., first turn), nothing is injected.
    """

    @property
    def name(self) -> str:
        return "runtime_state"

    def __init__(self) -> None:
        self._snapshot: StateSnapshot | None = None

    def set_snapshot(self, snapshot: StateSnapshot) -> None:
        """Called by CoreRuntime before context assembly begins."""
        self._snapshot = snapshot

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        if self._snapshot is None:
            return context

        snap = self._snapshot
        lines = [
            f"Runtime state:",
            f"  run_id={snap.current_run_id or 'none'}",
            f"  state={snap.run_state.value}",
            f"  framework={snap.framework_name}",
            f"  context_tokens={snap.context_token_count}",
            f"  checkpoint_available={snap.checkpoint_available}",
        ]
        if snap.active_callable:
            lines.append(f"  active_callable={snap.active_callable}")

        content = "\n".join(lines)
        token_count = _estimate_tokens(content)

        source = ContextSource(
            source_type="state",
            content=content,
            token_count=token_count,
            metadata={
                "run_id": snap.current_run_id,
                "run_state": snap.run_state.value,
                "framework": snap.framework_name,
            },
        )

        return context.model_copy(
            update={
                "sources": context.sources + [source],
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": context.budget_remaining - token_count,
            }
        )
