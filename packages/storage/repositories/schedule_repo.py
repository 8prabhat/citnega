"""ScheduleRepository — persist and retrieve ScheduledRun entries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from citnega.packages.protocol.models.scheduler import ScheduledRun
from citnega.packages.storage.repositories.base import BaseRepository


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _parse_dt_opt(s: str | None) -> datetime | None:
    return _parse_dt(s) if s else None


class ScheduleRepository(BaseRepository[ScheduledRun]):
    _table = "scheduled_runs"
    _id_field = "schedule_id"

    def _from_row(self, row: dict[str, Any]) -> ScheduledRun:
        return ScheduledRun(
            schedule_id=row["schedule_id"],
            name=row["name"],
            schedule=row["schedule"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            enabled=bool(row["enabled"]),
            last_fired_at=_parse_dt_opt(row.get("last_fired_at")),
            next_fire_at=_parse_dt_opt(row.get("next_fire_at")),
            created_at=_parse_dt(row["created_at"]),
        )

    def _to_row(self, entity: ScheduledRun) -> dict[str, Any]:
        return {
            "schedule_id": entity.schedule_id,
            "name": entity.name,
            "schedule": entity.schedule,
            "session_id": entity.session_id,
            "prompt": entity.prompt,
            "enabled": int(entity.enabled),
            "last_fired_at": entity.last_fired_at.isoformat() if entity.last_fired_at else None,
            "next_fire_at": entity.next_fire_at.isoformat() if entity.next_fire_at else None,
            "created_at": entity.created_at.isoformat(),
        }

    async def save(self, entity: ScheduledRun) -> ScheduledRun:
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

    async def list(self, **filters: object) -> list[ScheduledRun]:
        where_clauses: list[str] = []
        params: list[object] = []

        enabled = filters.get("enabled")
        if enabled is not None:
            where_clauses.append("enabled = ?")
            params.append(int(enabled))

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        rows = await self._db.fetchall(
            f"SELECT * FROM {self._table} {where} ORDER BY created_at ASC",
            tuple(params),
        )
        return [self._from_row(r) for r in rows]

    async def update_last_fired(self, schedule_id: str, fired_at: datetime) -> None:
        async with self._db.write_lock:
            await self._db.execute(
                "UPDATE scheduled_runs SET last_fired_at = ?, enabled = "
                "CASE WHEN schedule = 'once' THEN 0 ELSE enabled END "
                "WHERE schedule_id = ?",
                (fired_at.isoformat(), schedule_id),
            )
