"""SessionSummaryHandler — injects a session summary from stored run history."""

from __future__ import annotations

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource
from citnega.packages.protocol.models.runs import TERMINAL_RUN_STATES
from citnega.packages.protocol.models.sessions import Session
from citnega.packages.storage.repositories.run_repo import RunRepository


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class SessionSummaryHandler(IContextHandler):
    """
    Builds a lightweight session summary by scanning recent completed runs.

    The summary covers: total runs, successful/failed counts, and the last
    few run states — giving the model a sense of session history without
    re-feeding all messages.

    This is a Phase 2 lightweight summary.  Phase 8 (KB v1) will replace
    this with a proper rolling summary from the run_summaries table.
    """

    @property
    def name(self) -> str:
        return "session_summary"

    def __init__(
        self,
        run_repo: RunRepository,
        max_runs_to_scan: int = 10,
    ) -> None:
        self._repo = run_repo
        self._max_runs = max_runs_to_scan

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
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
            lines.append(f"  [{ts}] run={r.run_id[:8]} state={r.state.value} "
                          f"turns={r.turn_count}")

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
                "sources": context.sources + [source],
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": context.budget_remaining - token_count,
            }
        )
