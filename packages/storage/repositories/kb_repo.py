"""KBRepository — kb_items and kb_fts tables."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from citnega.packages.protocol.models.kb import KBItem, KBSearchResult, KBSourceType
from citnega.packages.storage.repositories.base import BaseRepository

_BM25_SEARCH_SQL = """
    SELECT
        i.*,
        snippet(kb_fts, 2, '[', ']', '...', 12) AS snippet,
        bm25(kb_fts) AS score
    FROM kb_fts
    JOIN kb_items i ON i.item_id = kb_fts.item_id
    WHERE kb_fts MATCH ?
    ORDER BY score
    LIMIT ?
"""


class KBRepository(BaseRepository[KBItem]):
    _table = "kb_items"
    _id_field = "item_id"

    def _from_row(self, row: dict[str, Any]) -> KBItem:
        return KBItem(
            item_id=row["item_id"],
            title=row["title"],
            content=row["content"],
            source_type=KBSourceType(row["source_type"]),
            source_session_id=row.get("source_session_id"),
            source_run_id=row.get("source_run_id"),
            tags=json.loads(row.get("tags") or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=UTC),
            updated_at=datetime.fromisoformat(row["updated_at"]).replace(tzinfo=UTC),
            content_hash=row["content_hash"],
            file_path=row.get("file_path"),
        )

    def _to_row(self, entity: KBItem) -> dict[str, Any]:
        return {
            "item_id": entity.item_id,
            "title": entity.title,
            "content": entity.content,
            "source_type": entity.source_type.value,
            "source_session_id": entity.source_session_id,
            "source_run_id": entity.source_run_id,
            "tags": json.dumps(entity.tags),
            "created_at": entity.created_at.isoformat(),
            "updated_at": entity.updated_at.isoformat(),
            "content_hash": entity.content_hash,
            "file_path": entity.file_path,
        }

    async def save(self, entity: KBItem) -> KBItem:
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

    async def list(self, **filters: object) -> list[KBItem]:
        clauses: list[str] = []
        params: list[object] = []
        tags = filters.get("tags")
        source_type = filters.get("source_type")
        limit = int(filters.get("limit", 100))

        # Tag filtering is done post-query (JSON array in column)
        if source_type:
            clauses.append("source_type = ?")
            params.append(str(source_type))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = await self._db.fetchall(
            f"SELECT * FROM {self._table} {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        items = [self._from_row(r) for r in rows]

        # Filter by tags if requested
        if tags and isinstance(tags, list):
            items = [item for item in items if any(t in item.tags for t in tags)]
        return items

    async def search(self, query: str, limit: int = 10) -> list[KBSearchResult]:
        """FTS5 BM25-ranked search."""
        # Escape special FTS5 characters
        safe_query = query.replace('"', '""')
        rows = await self._db.fetchall(_BM25_SEARCH_SQL, (safe_query, limit))
        results: list[KBSearchResult] = []
        for row in rows:
            item = self._from_row(row)
            results.append(
                KBSearchResult(
                    item=item,
                    score=float(row.get("score", 0.0)),
                    snippet=str(row.get("snippet", "")),
                )
            )
        return results

    async def find_by_hash(self, content_hash: str) -> KBItem | None:
        row = await self._db.fetchone(
            "SELECT * FROM kb_items WHERE content_hash = ?",
            (content_hash,),
        )
        return self._from_row(row) if row else None
