"""SessionSummaryHandler — injects a session summary and performs LLM rolling compaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.protocol.models.runs import TERMINAL_RUN_STATES

if TYPE_CHECKING:
    from citnega.packages.protocol.models.sessions import Session
    from citnega.packages.storage.repositories.run_repo import RunRepository

_COMPACTED_PREFIX = "[Summary of earlier conversation:"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class SessionSummaryHandler(IContextHandler):
    """
    Builds a lightweight session summary by scanning recent completed runs.

    When the active conversation exceeds `summarize_threshold` messages and a
    model_gateway is available, compacts the oldest `summarize_window` messages
    into a single summary message — reducing token usage on long sessions.
    """

    parallel_safe = True

    @property
    def name(self) -> str:
        return "session_summary"

    def __init__(
        self,
        run_repo: RunRepository,
        max_runs_to_scan: int = 10,
        model_gateway: object | None = None,
        conversation_store: object | None = None,
        summarize_threshold: int = 20,
        summarize_window: int = 15,
    ) -> None:
        self._repo = run_repo
        self._max_runs = max_runs_to_scan
        self._model_gateway = model_gateway
        self._conversation_store = conversation_store
        self._summarize_threshold = summarize_threshold
        self._summarize_window = summarize_window

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        # Rolling compaction (best-effort — never blocks on failure)
        if self._model_gateway is not None and self._conversation_store is not None:
            try:
                await self._maybe_compact(session)
            except Exception as exc:
                runtime_logger.warning("session_summary_compact_failed", error=str(exc))

        runs = await self._repo.list(
            session_id=session.config.session_id,
            limit=self._max_runs,
        )

        if not runs:
            return context

        completed = [r for r in runs if r.state in TERMINAL_RUN_STATES]
        failed = sum(1 for r in completed if r.state.value == "failed")
        ok = len(completed) - failed

        lines = [
            f"Session: {session.config.name} (total runs: {len(completed)}, "
            f"ok: {ok}, failed: {failed})",
        ]
        for r in runs[:5]:
            ts = r.started_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"  [{ts}] run={r.run_id[:8]} state={r.state.value} turns={r.turn_count}")

        content = "\n".join(lines)
        token_count = _estimate_tokens(content)

        source = ContextSource(
            source_type="summary",
            content=content,
            token_count=token_count,
            metadata={"run_count": len(completed)},
        )

        runtime_logger.debug(
            "context_session_summary",
            session_id=session.config.session_id,
            run_count=len(completed),
        )

        return context.model_copy(
            update={
                "sources": [*context.sources, source],
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": context.budget_remaining - token_count,
            }
        )

    async def _maybe_compact(self, session: Session) -> None:
        messages = self._conversation_store.get_messages()  # type: ignore[union-attr]
        if len(messages) <= self._summarize_threshold:
            return

        # Skip if already compacted (first assistant message is a summary)
        first_content = next(
            (m.get("content", "") for m in messages if m.get("role") == "assistant"), ""
        )
        if first_content.startswith(_COMPACTED_PREFIX):
            return

        window = messages[: self._summarize_window]
        combined = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')[:400]}" for m in window
        )
        prompt = (
            "Summarize this conversation excerpt in 3-5 sentences. Be concise and factual.\n\n"
            + combined
        )

        try:
            from citnega.packages.protocol.models.model_gateway import ModelRequest, ModelMessage

            req = ModelRequest(
                messages=[ModelMessage(role="user", content=prompt)],
                temperature=0.3,
                max_tokens=300,
                stream=False,
            )
            response = await self._model_gateway.generate(req)  # type: ignore[union-attr]
            summary_text = getattr(response, "content", "").strip()
            if not summary_text:
                return
        except Exception:
            return

        summary_msg = f"{_COMPACTED_PREFIX} {summary_text}]"
        try:
            await self._conversation_store.compact(  # type: ignore[union-attr]
                summary_msg, keep_recent=len(messages) - self._summarize_window
            )
            runtime_logger.info(
                "session_compacted",
                session_id=session.config.session_id,
                turns_compacted=self._summarize_window,
            )
        except Exception as exc:
            runtime_logger.warning("session_compact_write_failed", error=str(exc))
