"""SpanRepository — persists TraceSpan records to the trace_spans table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.runtime.tracing.span import TraceSpan
from citnega.packages.storage.repositories.base import BaseRepository

if TYPE_CHECKING:
    from citnega.packages.storage.database import DatabaseFactory


class SpanRepository(BaseRepository[TraceSpan]):
    _table = "trace_spans"
    _id_field = "span_id"

    def _from_row(self, row: dict[str, Any]) -> TraceSpan:
        return TraceSpan(
            span_id=row["span_id"],
            run_id=row["run_id"],
            turn_id=row.get("turn_id"),
            step_id=row.get("step_id"),
            tool_name=row["tool_name"],
            start_ts=row["start_ts"],
            end_ts=row["end_ts"],
            input_hash=row.get("input_hash", ""),
            output_hash=row.get("output_hash", ""),
            success=bool(row.get("success", 1)),
        )

    def _to_row(self, entity: TraceSpan) -> dict[str, Any]:
        return {
            "span_id": entity.span_id,
            "run_id": entity.run_id,
            "turn_id": entity.turn_id,
            "step_id": entity.step_id,
            "tool_name": entity.tool_name,
            "start_ts": entity.start_ts,
            "end_ts": entity.end_ts,
            "input_hash": entity.input_hash,
            "output_hash": entity.output_hash,
            "success": 1 if entity.success else 0,
        }

    async def save(self, entity: TraceSpan) -> TraceSpan:
        row = self._to_row(entity)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k} = excluded.{k}" for k in row if k != self._id_field)
        sql = (
            f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT({self._id_field}) DO UPDATE SET {updates}"
        )
        async with self._db.write_lock:
            await self._db.execute(sql, tuple(row.values()))
        return entity

    async def list(self, run_id: str, limit: int = 200) -> list[TraceSpan]:
        rows = await self._db.fetchall(
            f"SELECT * FROM {self._table} WHERE run_id = ? ORDER BY start_ts LIMIT ?",
            (run_id, limit),
        )
        return [self._from_row(r) for r in rows]
