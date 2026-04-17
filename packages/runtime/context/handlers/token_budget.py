"""
TokenBudgetHandler — enforces max_context_tokens and marks truncation.

This handler must be the LAST in the chain.  It trims sources from the
end (lowest priority) until total_tokens ≤ max_context_tokens, then
sets ``truncated=True`` if any source was dropped.

Priority order (highest = kept first):
  recent_turns > runtime_state > summary > kb > everything else

Sources with higher priority values survive trimming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from citnega.packages.model_gateway.token_counter import CharApproxCounter
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler

_token_counter = CharApproxCounter()

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.events import IEventEmitter
    from citnega.packages.protocol.models.context import ContextObject, ContextSource
    from citnega.packages.protocol.models.sessions import Session

_PRIORITY_DEFAULTS: dict[str, int] = {
    "recent_turns": 100,
    "state": 80,
    "summary": 60,
    "kb": 40,
}

_DEFAULT_PRIORITY = 20


class TokenBudgetHandler(IContextHandler):
    """
    Last-in-chain handler that enforces the session's max_context_tokens.

    Drops lowest-priority sources until the budget is satisfied.
    """

    @property
    def name(self) -> str:
        return "token_budget"

    def __init__(
        self,
        max_context_tokens: int = 8192,
        emitter: IEventEmitter | None = None,
        priorities: dict[str, int] | None = None,
        default_priority: int = _DEFAULT_PRIORITY,
    ) -> None:
        self._max_tokens = max_context_tokens
        self._emitter = emitter
        self._priorities = priorities if priorities is not None else dict(_PRIORITY_DEFAULTS)
        self._default_priority = default_priority

    def _priority(self, source: ContextSource) -> int:
        return self._priorities.get(source.source_type, self._default_priority)

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        max_tokens = session.config.max_context_tokens or self._max_tokens
        # Also reserve tokens for the user input itself
        user_input_tokens = _token_counter.count(context.user_input)
        budget = max_tokens - user_input_tokens

        if context.total_tokens <= budget:
            # No trimming needed
            return context.model_copy(update={"budget_remaining": budget - context.total_tokens})

        # Sort by priority (highest first), then trim from the back
        sources = sorted(context.sources, key=self._priority, reverse=True)
        kept: list[ContextSource] = []
        running_total = 0
        truncated = False

        dropped_sources: list[str] = []
        for source in sources:
            if running_total + source.token_count <= budget:
                kept.append(source)
                running_total += source.token_count
            else:
                truncated = True
                dropped_sources.append(source.source_type)

        if truncated:
            runtime_logger.warning(
                "context_token_budget_truncated",
                session_id=session.config.session_id,
                dropped_sources=dropped_sources,
                total_before=context.total_tokens,
                total_after=running_total,
                budget=budget,
            )
            if self._emitter is not None:
                from citnega.packages.protocol.events.context import ContextTruncatedEvent

                self._emitter.emit(
                    ContextTruncatedEvent(
                        session_id=context.session_id,
                        run_id=context.run_id,
                        before_tokens=context.total_tokens,
                        after_tokens=running_total,
                        budget_tokens=budget,
                        dropped_sources=dropped_sources,
                    )
                )

        # Restore insertion order within kept sources
        kept_sorted = sorted(kept, key=lambda s: context.sources.index(s))

        return context.model_copy(
            update={
                "sources": kept_sorted,
                "total_tokens": running_total,
                "budget_remaining": budget - running_total,
                "truncated": truncated,
            }
        )
