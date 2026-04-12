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

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler

if TYPE_CHECKING:
    from citnega.packages.protocol.models.context import ContextObject, ContextSource
    from citnega.packages.protocol.models.sessions import Session

_PRIORITY: dict[str, int] = {
    "recent_turns": 100,
    "state": 80,
    "summary": 60,
    "kb": 40,
}

_DEFAULT_PRIORITY = 20


def _priority(source: ContextSource) -> int:
    return _PRIORITY.get(source.source_type, _DEFAULT_PRIORITY)


class TokenBudgetHandler(IContextHandler):
    """
    Last-in-chain handler that enforces the session's max_context_tokens.

    Drops lowest-priority sources until the budget is satisfied.
    """

    @property
    def name(self) -> str:
        return "token_budget"

    def __init__(self, max_context_tokens: int = 8192) -> None:
        self._max_tokens = max_context_tokens

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        max_tokens = session.config.max_context_tokens or self._max_tokens
        # Also reserve ~128 tokens for the user input itself
        user_input_tokens = max(1, len(context.user_input) // 4)
        budget = max_tokens - user_input_tokens

        if context.total_tokens <= budget:
            # No trimming needed
            return context.model_copy(update={"budget_remaining": budget - context.total_tokens})

        # Sort by priority (highest first), then trim from the back
        sources = sorted(context.sources, key=_priority, reverse=True)
        kept: list[ContextSource] = []
        running_total = 0
        truncated = False

        for source in sources:
            if running_total + source.token_count <= budget:
                kept.append(source)
                running_total += source.token_count
            else:
                truncated = True
                runtime_logger.warning(
                    "context_token_budget_truncated",
                    session_id=session.config.session_id,
                    dropped_source=source.source_type,
                    total_before=context.total_tokens,
                    budget=budget,
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
