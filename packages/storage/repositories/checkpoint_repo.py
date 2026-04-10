"""CheckpointRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from citnega.packages.protocol.models.checkpoints import CheckpointMeta
from citnega.packages.storage.repositories.base import BaseRepository


class CheckpointRepository(BaseRepository[CheckpointMeta]):
    _table    = "checkpoints"
    _id_field = "checkpoint_id"

    def _from_row(self, row: dict[str, Any]) -> CheckpointMeta:
        return CheckpointMeta(
            checkpoint_id=row["checkpoint_id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            created_at=datetime.fromisoformat(row["created_at"]).replace(
                tzinfo=timezone.utc
            ),
            framework_name=row["framework_name"],
            file_path=row["file_path"],
            size_bytes=row["size_bytes"],
            state_summary=row["state_summary"],
        )

    def _to_row(self, entity: CheckpointMeta) -> dict[str, Any]:
        return {
            "checkpoint_id":  entity.checkpoint_id,
            "session_id":     entity.session_id,
            "run_id":         entity.run_id,
            "created_at":     entity.created_at.isoformat(),
            "framework_name": entity.framework_name,
            "file_path":      entity.file_path,
            "size_bytes":     entity.size_bytes,
            "state_summary":  entity.state_summary,
        }

    async def save(self, entity: CheckpointMeta) -> CheckpointMeta:
        row = self._to_row(entity)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT OR REPLACE INTO {self._table} ({cols}) VALUES ({placeholders})"
        async with self._db.write_lock:
            await self._db.execute(sql, tuple(row.values()))
        return entity

    async def list(self, **filters: object) -> list[CheckpointMeta]:
        session_id = filters.get("session_id")
        rows = await self._db.fetchall(
            "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ) if session_id else await self._db.fetchall(
            "SELECT * FROM checkpoints ORDER BY created_at DESC"
        )
        return [self._from_row(r) for r in rows]
