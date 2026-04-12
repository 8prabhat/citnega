"""RunRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from citnega.packages.protocol.models.runs import RunState, RunSummary
from citnega.packages.storage.repositories.base import BaseRepository


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _parse_dt_opt(s: str | None) -> datetime | None:
    return _parse_dt(s) if s else None


class RunRepository(BaseRepository[RunSummary]):
    _table = "runs"
    _id_field = "run_id"

    def _from_row(self, row: dict[str, Any]) -> RunSummary:
        return RunSummary(
            run_id=row["run_id"],
            session_id=row["session_id"],
            state=RunState(row["state"]),
            started_at=_parse_dt(row["started_at"]),
            finished_at=_parse_dt_opt(row.get("finished_at")),
            turn_count=row["turn_count"],
            total_tokens=row["total_tokens"],
            error=row.get("error_message"),
        )

    def _to_row(self, entity: RunSummary) -> dict[str, Any]:
        return {
            "run_id": entity.run_id,
            "session_id": entity.session_id,
            "state": entity.state.value,
            "started_at": entity.started_at.isoformat(),
            "finished_at": entity.finished_at.isoformat() if entity.finished_at else None,
            "turn_count": entity.turn_count,
            "total_tokens": entity.total_tokens,
            "error_message": entity.error,
        }

    async def save(self, entity: RunSummary) -> RunSummary:
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

    async def list(self, **filters: object) -> list[RunSummary]:
        session_id = filters.get("session_id")
        limit = int(filters.get("limit", 50))
        if session_id:
            rows = await self._db.fetchall(
                "SELECT * FROM runs WHERE session_id = ? ORDER BY started_at DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        return [self._from_row(r) for r in rows]
