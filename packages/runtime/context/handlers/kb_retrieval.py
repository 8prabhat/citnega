"""
KBRetrievalHandler — injects relevant KB snippets into the context.

Queries IKnowledgeStore for the top-K items matching the user's input and
appends them as a ContextSource so the framework runner can include them
in the LLM prompt.

Falls back gracefully when:
  - ``kb_store`` is None (store not injected — no-op)
  - ``kb_enabled`` is False on the session config
  - The FTS search returns no results
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.knowledge_store import IKnowledgeStore
    from citnega.packages.protocol.models.sessions import Session

from citnega.packages.model_gateway.token_counter import CharApproxCounter

_token_counter = CharApproxCounter()


class KBRetrievalHandler(IContextHandler):
    """
    Real KB handler (Phase 8).

    Args:
        kb_store:      Injected IKnowledgeStore.  If None, handler is a no-op.
        retrieve_limit: Max KB items to include per turn.
    """

    @property
    def name(self) -> str:
        return "kb_retrieval"

    def __init__(
        self,
        kb_store: IKnowledgeStore | None = None,
        retrieve_limit: int = 5,
    ) -> None:
        self._kb_store = kb_store
        self._retrieve_limit = retrieve_limit

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        if self._kb_store is None:
            return context
        if not session.config.kb_enabled:
            return context

        query = context.user_input
        if not query.strip():
            return context

        try:
            results = await self._kb_store.search(query, limit=self._retrieve_limit)
        except Exception:
            return context  # KB errors are non-fatal

        if not results:
            return context

        # Build one ContextSource for all KB snippets combined
        snippets = "\n\n".join(f"[KB: {r.item.title}]\n{r.item.content}" for r in results)
        token_count = _token_counter.count(snippets)

        new_source = ContextSource(
            source_type="kb",
            content=snippets,
            token_count=token_count,
            metadata={
                "result_count": len(results),
                "top_score": results[0].score if results else 0.0,
            },
        )

        updated_sources = [*list(context.sources), new_source]
        return context.model_copy(
            update={
                "sources": updated_sources,
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": max(0, context.budget_remaining - token_count),
            }
        )
