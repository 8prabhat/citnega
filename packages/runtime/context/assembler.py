"""
ContextAssembler — Chain-of-Responsibility context pipeline.

Assembly runs the configured handler chain in order.  Each handler adds
ContextSource entries to the ContextObject.  The final handler
(TokenBudgetHandler) enforces the token limit and marks truncation.

Handler chain (configured in settings.toml [context].handlers):
  1. RecentTurnsHandler   — recent messages
  2. SessionSummaryHandler — run history summary
  3. KBRetrievalHandler   — KB snippets (stub in Phase 2)
  4. RuntimeStateHandler  — current run snapshot
  5. TokenBudgetHandler   — trim to fit token budget (must be last)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextAssembler, IContextHandler
from citnega.packages.protocol.models.context import ContextObject
from citnega.packages.shared.errors import CitnegaError

if TYPE_CHECKING:
    from citnega.packages.protocol.models.sessions import Session


class ContextAssembler(IContextAssembler):
    """
    Concrete IContextAssembler that runs an ordered list of IContextHandlers.

    Handlers are injected at construction time by the bootstrap (or test
    fixtures).  Order matters: TokenBudgetHandler MUST be last.

    Parameters
    ----------
    handlers
        Ordered list of context handlers to run.
    handler_timeout_ms
        Per-handler timeout in milliseconds.  0 (default) = no timeout.
        When a handler exceeds its budget it is skipped with a warning,
        same as any other handler error.
    """

    def __init__(
        self,
        handlers: list[IContextHandler],
        handler_timeout_ms: int = 0,
    ) -> None:
        if not handlers:
            raise ValueError("ContextAssembler requires at least one handler.")
        self._handlers = handlers
        self._handler_timeout_s: float | None = (
            handler_timeout_ms / 1000.0 if handler_timeout_ms > 0 else None
        )

    @property
    def handlers(self) -> list[IContextHandler]:
        """Read-only view of the handler chain (for introspection)."""
        return list(self._handlers)

    async def assemble(
        self,
        session: Session,
        user_input: str,
        run_id: str,
    ) -> ContextObject:
        """
        Run the full handler chain and return a fully-assembled ContextObject.

        A handler that raises is logged and skipped so that a single broken
        handler does not abort the entire turn.  TokenBudgetHandler errors
        are re-raised because they indicate a configuration problem.
        """
        max_tokens = session.config.max_context_tokens
        context = ContextObject(
            session_id=session.config.session_id,
            run_id=run_id,
            user_input=user_input,
            assembled_at=datetime.now(tz=UTC),
            budget_remaining=max_tokens,
        )

        for handler in self._handlers:
            try:
                coro = handler.enrich(context, session)
                if self._handler_timeout_s is not None:
                    context = await asyncio.wait_for(coro, timeout=self._handler_timeout_s)
                else:
                    context = await coro
            except TimeoutError:
                runtime_logger.warning(
                    "context_handler_timeout",
                    handler=handler.name,
                    session_id=session.config.session_id,
                    run_id=run_id,
                    timeout_s=self._handler_timeout_s,
                )
                # Skip timed-out handler; context is unchanged
            except CitnegaError:
                # Re-raise policy / config errors
                raise
            except Exception as exc:
                runtime_logger.warning(
                    "context_handler_error",
                    handler=handler.name,
                    session_id=session.config.session_id,
                    run_id=run_id,
                    error=str(exc),
                )
                # Skip broken handler; context is unchanged

        runtime_logger.debug(
            "context_assembled",
            session_id=session.config.session_id,
            run_id=run_id,
            total_tokens=context.total_tokens,
            sources=[s.source_type for s in context.sources],
            truncated=context.truncated,
        )

        return context
