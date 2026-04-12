"""MessageRepository."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from citnega.packages.protocol.models.messages import Message, MessageRole
from citnega.packages.storage.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    _table = "messages"
    _id_field = "message_id"

    def _from_row(self, row: dict[str, Any]) -> Message:
        return Message(
            message_id=row["message_id"],
            session_id=row["session_id"],
            run_id=row.get("run_id"),
            role=MessageRole(row["role"]),
            content=row["content"],
            timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=UTC),
            metadata=json.loads(row.get("metadata") or "{}"),
        )

    def _to_row(self, entity: Message) -> dict[str, Any]:
        return {
            "message_id": entity.message_id,
            "session_id": entity.session_id,
            "run_id": entity.run_id,
            "role": entity.role.value,
            "content": entity.content,
            "timestamp": entity.timestamp.isoformat(),
            "metadata": json.dumps(entity.metadata),
        }

    async def save(self, entity: Message) -> Message:
        row = self._to_row(entity)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT OR REPLACE INTO {self._table} ({cols}) VALUES ({placeholders})"
        async with self._db.write_lock:
            await self._db.execute(sql, tuple(row.values()))
        return entity

    async def list(self, **filters: object) -> list[Message]:
        session_id = filters.get("session_id")
        limit = int(filters.get("limit", 100))
        if session_id:
            rows = await self._db.fetchall(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT * FROM messages ORDER BY timestamp ASC LIMIT ?",
                (limit,),
            )
        return [self._from_row(r) for r in rows]
