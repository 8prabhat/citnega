"""SessionRepository — persist and retrieve Session entities."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
from citnega.packages.storage.repositories.base import BaseRepository


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


class SessionRepository(BaseRepository[Session]):
    _table = "sessions"
    _id_field = "session_id"

    def _from_row(self, row: dict[str, Any]) -> Session:
        config = SessionConfig.model_validate(json.loads(row["config_json"]))
        return Session(
            config=config,
            created_at=_parse_dt(row["created_at"]),
            last_active_at=_parse_dt(row["last_active_at"]),
            run_count=row["run_count"],
            state=SessionState(row["state"]),
        )

    def _to_row(self, entity: Session) -> dict[str, Any]:
        cfg = entity.config
        return {
            "session_id": cfg.session_id,
            "name": cfg.name,
            "framework": cfg.framework,
            "default_model_id": cfg.default_model_id,
            "local_only": int(cfg.local_only),
            "max_callable_depth": cfg.max_callable_depth,
            "kb_enabled": int(cfg.kb_enabled),
            "max_context_tokens": cfg.max_context_tokens,
            "approval_timeout_seconds": cfg.approval_timeout_seconds,
            "tags": json.dumps(cfg.tags),
            "config_json": cfg.model_dump_json(),
            "state": entity.state.value,
            "created_at": entity.created_at.isoformat(),
            "last_active_at": entity.last_active_at.isoformat(),
            "run_count": entity.run_count,
        }

    async def save(self, entity: Session) -> Session:
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

    async def list(self, **filters: object) -> list[Session]:
        where_clauses: list[str] = []
        params: list[object] = []
        limit = int(filters.pop("limit", 100))

        for key, val in filters.items():
            where_clauses.append(f"{key} = ?")
            params.append(val)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"SELECT * FROM {self._table} {where} ORDER BY last_active_at DESC LIMIT ?"
        params.append(limit)
        rows = await self._db.fetchall(sql, tuple(params))
        return [self._from_row(r) for r in rows]
