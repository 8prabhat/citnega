"""
Tracer — records callable invocations to callable_invocations table.

Called from BaseCallable.invoke() after every execution (success or failure).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
from typing import TYPE_CHECKING
import uuid

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.events import ITracer
from citnega.packages.storage.repositories.invocation_repo import (
    InvocationRecord,
    InvocationRepository,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.results import InvokeResult


class Tracer(ITracer):
    """
    Records callable invocations asynchronously.

    ``record()`` is synchronous (per ITracer contract) — it schedules
    the DB write as a background task on the running event loop.
    """

    def __init__(
        self,
        invocation_repo: InvocationRepository,
        span_repo: object | None = None,
    ) -> None:
        self._repo = invocation_repo
        self._span_repo = span_repo  # SpanRepository | None

    def record(
        self,
        callable: IInvocable,
        input: BaseModel,
        result: InvokeResult,
        context: CallContext,
    ) -> None:
        """Schedule DB write non-blockingly. Never raises."""
        try:
            invocation_id = str(uuid.uuid4())
            input_json = input.model_dump_json()
            input_hash = hashlib.sha256(input_json.encode()).hexdigest()[:16]
            input_summary = input_json[:256]

            rec = InvocationRecord(
                invocation_id=invocation_id,
                run_id=context.run_id,
                callable_name=callable.name,
                callable_type=callable.callable_type.value,
                depth=context.depth,
                parent_invocation_id=None,
                input_hash=input_hash,
                input_summary=input_summary,
                output_size=(len(result.output.model_dump_json().encode()) if result.output else 0),
                duration_ms=result.duration_ms,
                policy_result="passed" if result.success else "failed",
                error_code=result.error.error_code if result.error else None,
                started_at=datetime.now(tz=UTC).isoformat(),
                finished_at=datetime.now(tz=UTC).isoformat(),
            )

            # Schedule on the running loop (non-blocking)
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(self._save(rec))
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

                # Also save a TraceSpan if span_repo is wired
                if self._span_repo is not None:
                    output_hash = ""
                    if result.output:
                        out_json = result.output.model_dump_json()
                        output_hash = hashlib.sha256(out_json.encode()).hexdigest()[:16]
                    span_task = loop.create_task(
                        self._save_span(
                            invocation_id=invocation_id,
                            callable_name=callable.name,
                            run_id=context.run_id,
                            turn_id=getattr(context, "turn_id", None),
                            step_id=None,
                            input_hash=input_hash,
                            output_hash=output_hash,
                            success=result.success,
                            duration_ms=result.duration_ms,
                        )
                    )
                    span_task.add_done_callback(
                        lambda t: t.exception() if not t.cancelled() else None
                    )
            except RuntimeError:
                # No running loop — skip tracing (e.g., in sync test context)
                pass

        except Exception as exc:
            runtime_logger.warning("tracer_record_failed", error=str(exc))

    async def _save(self, rec: InvocationRecord) -> None:
        try:
            await self._repo.save(rec)
        except Exception as exc:
            runtime_logger.warning("tracer_save_failed", error=str(exc))

    async def _save_span(
        self,
        *,
        invocation_id: str,
        callable_name: str,
        run_id: str,
        turn_id: str | None,
        step_id: str | None,
        input_hash: str,
        output_hash: str,
        success: bool,
        duration_ms: int,
    ) -> None:
        try:
            from datetime import timedelta
            from citnega.packages.runtime.tracing.span import TraceSpan

            now = datetime.now(tz=UTC)
            start = (now - timedelta(milliseconds=duration_ms)).isoformat()
            span = TraceSpan(
                span_id=invocation_id,
                run_id=run_id,
                turn_id=turn_id,
                step_id=step_id,
                tool_name=callable_name,
                start_ts=start,
                end_ts=now.isoformat(),
                input_hash=input_hash,
                output_hash=output_hash,
                success=success,
            )
            await self._span_repo.save(span)  # type: ignore[union-attr]
        except Exception as exc:
            runtime_logger.warning("tracer_span_save_failed", error=str(exc))
