"""
Tracer — records callable invocations to callable_invocations table.

Called from BaseCallable.invoke() after every execution (success or failure).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.interfaces.events import ITracer
from citnega.packages.storage.repositories.invocation_repo import (
    InvocationRecord,
    InvocationRepository,
)


class Tracer(ITracer):
    """
    Records callable invocations asynchronously.

    ``record()`` is synchronous (per ITracer contract) — it schedules
    the DB write as a background task on the running event loop.
    """

    def __init__(self, invocation_repo: InvocationRepository) -> None:
        self._repo = invocation_repo

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
            input_json    = input.model_dump_json()
            input_hash    = hashlib.sha256(input_json.encode()).hexdigest()[:16]
            input_summary = input_json[:256]

            rec = InvocationRecord(
                invocation_id         = invocation_id,
                run_id                = context.run_id,
                callable_name         = callable.name,
                callable_type         = callable.callable_type.value,
                depth                 = context.depth,
                parent_invocation_id  = None,
                input_hash            = input_hash,
                input_summary         = input_summary,
                output_size           = (
                    len(result.output.model_dump_json().encode())
                    if result.output else 0
                ),
                duration_ms           = result.duration_ms,
                policy_result         = "passed" if result.success else "failed",
                error_code            = result.error.error_code if result.error else None,
                started_at            = datetime.now(tz=timezone.utc).isoformat(),
                finished_at           = datetime.now(tz=timezone.utc).isoformat(),
            )

            # Schedule on the running loop (non-blocking)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._save(rec))
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
