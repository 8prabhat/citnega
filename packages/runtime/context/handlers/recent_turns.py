"""RecentTurnsHandler — injects the N most recent turn messages as context."""

from __future__ import annotations

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.protocol.models.sessions import Session
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.storage.repositories.message_repo import MessageRepository


def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 characters per token (GPT-style)."""
    return max(1, len(text) // 4)


class RecentTurnsHandler(IContextHandler):
    """
    Fetches the most recent *n* messages for the session and adds them
    as a "recent_turns" ContextSource.
    """

    @property
    def name(self) -> str:
        return "recent_turns"

    def __init__(
        self,
        message_repo: MessageRepository,
        recent_turns_count: int = 20,
    ) -> None:
        self._repo = message_repo
        self._count = recent_turns_count

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        messages = await self._repo.list(
            session_id=session.config.session_id,
            limit=self._count,
        )

        if not messages:
            return context

        # Format as a simple turn log
        lines: list[str] = []
        for msg in messages:
            role = msg.role.value.upper()
            lines.append(f"[{role}] {msg.content}")

        content = "\n".join(lines)
        token_count = _estimate_tokens(content)

        source = ContextSource(
            source_type="recent_turns",
            content=content,
            token_count=token_count,
            metadata={"message_count": len(messages)},
        )

        runtime_logger.debug(
            "context_recent_turns",
            session_id=session.config.session_id,
            message_count=len(messages),
            token_count=token_count,
        )

        return context.model_copy(
            update={
                "sources": context.sources + [source],
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": context.budget_remaining - token_count,
            }
        )
