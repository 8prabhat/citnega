"""ApprovalRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from citnega.packages.protocol.models.approvals import Approval, ApprovalStatus
from citnega.packages.storage.repositories.base import BaseRepository


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class ApprovalRepository(BaseRepository[Approval]):
    _table    = "approvals"
    _id_field = "approval_id"

    def _from_row(self, row: dict[str, Any]) -> Approval:
        return Approval(
            approval_id=row["approval_id"],
            run_id=row["run_id"],
            callable_name=row["callable_name"],
            input_summary=row["input_summary"],
            requested_at=_parse_dt(row["requested_at"]),
            responded_at=_parse_dt(row["responded_at"]) if row.get("responded_at") else None,
            status=ApprovalStatus(row["status"]),
            user_note=row.get("user_note"),
        )

    def _to_row(self, entity: Approval) -> dict[str, Any]:
        return {
            "approval_id":   entity.approval_id,
            "run_id":        entity.run_id,
            "callable_name": entity.callable_name,
            "input_summary": entity.input_summary,
            "requested_at":  entity.requested_at.isoformat(),
            "responded_at":  entity.responded_at.isoformat() if entity.responded_at else None,
            "status":        entity.status.value,
            "user_note":     entity.user_note,
        }

    async def save(self, entity: Approval) -> Approval:
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

    async def list(self, **filters: object) -> list[Approval]:
        run_id = filters.get("run_id")
        status = filters.get("status")
        params: list[object] = []
        clauses: list[str] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = await self._db.fetchall(
            f"SELECT * FROM {self._table} {where} ORDER BY requested_at ASC",
            tuple(params) if params else None,
        )
        return [self._from_row(r) for r in rows]
