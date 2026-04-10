"""InvocationRepository — callable_invocations table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from citnega.packages.storage.repositories.base import BaseRepository


class InvocationRecord:
    """Lightweight record type for callable_invocations (not a Pydantic model)."""

    __slots__ = (
        "invocation_id", "run_id", "callable_name", "callable_type",
        "depth", "parent_invocation_id", "input_hash", "input_summary",
        "output_size", "duration_ms", "policy_result", "error_code",
        "started_at", "finished_at",
    )

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class InvocationRepository(BaseRepository[InvocationRecord]):
    _table    = "callable_invocations"
    _id_field = "invocation_id"

    def _from_row(self, row: dict[str, Any]) -> InvocationRecord:
        return InvocationRecord(**row)

    def _to_row(self, entity: InvocationRecord) -> dict[str, Any]:
        return {slot: getattr(entity, slot, None) for slot in entity.__slots__}

    async def save(self, entity: InvocationRecord) -> InvocationRecord:
        row = {k: v for k, v in self._to_row(entity).items() if v is not None}
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT OR REPLACE INTO {self._table} ({cols}) VALUES ({placeholders})"
        async with self._db.write_lock:
            await self._db.execute(sql, tuple(row.values()))
        return entity

    async def list(self, **filters: object) -> list[InvocationRecord]:
        run_id = filters.get("run_id")
        if run_id:
            rows = await self._db.fetchall(
                "SELECT * FROM callable_invocations WHERE run_id = ? ORDER BY started_at ASC",
                (run_id,),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT * FROM callable_invocations ORDER BY started_at DESC LIMIT 200"
            )
        return [self._from_row(r) for r in rows]
