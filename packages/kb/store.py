"""
KnowledgeStore — concrete IKnowledgeStore backed by SQLite.

Responsibilities:
  - CRUD for kb_items (FTS5 triggers keep kb_fts in sync automatically)
  - Deduplication on content_hash (INSERT OR IGNORE)
  - BM25 search via retrieval module
  - Export via export module

All writes are serialised through DatabaseFactory.write_lock.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from citnega.packages.kb.export import default_export_path, export_jsonl
from citnega.packages.kb.retrieval import _row_to_item, fts_search
from citnega.packages.protocol.interfaces.knowledge_store import IKnowledgeStore

if TYPE_CHECKING:
    from pathlib import Path

    from citnega.packages.protocol.models.kb import KBItem, KBSearchResult, KBSourceType
    from citnega.packages.storage.database import DatabaseFactory
    from citnega.packages.storage.path_resolver import PathResolver


class KnowledgeStore(IKnowledgeStore):
    """
    SQLite-backed knowledge store.

    Args:
        db:            Shared DatabaseFactory (connection must be open).
        path_resolver: For resolving the kb_exports_dir.
    """

    def __init__(self, db: DatabaseFactory, path_resolver: PathResolver) -> None:
        self._db = db
        self._pr = path_resolver

    # ── IKnowledgeStore ────────────────────────────────────────────────────────

    async def add_item(self, item: KBItem) -> KBItem:
        """
        Persist *item*.

        If an item with the same ``content_hash`` already exists, the
        existing item is returned without modification (deduplication).
        """
        existing = await self._get_by_hash(item.content_hash)
        if existing is not None:
            return existing

        row = _item_to_row(item)
        cols = ", ".join(row.keys())
        holes = ", ".join("?" for _ in row)
        sql = f"INSERT OR IGNORE INTO kb_items ({cols}) VALUES ({holes})"

        async with self._db.write_lock:
            await self._db.execute(sql, tuple(row.values()))

        return item

    async def get_item(self, item_id: str) -> KBItem | None:
        row = await self._db.fetchone("SELECT * FROM kb_items WHERE item_id = ?", (item_id,))
        return _row_to_item(row) if row else None

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[KBSearchResult]:
        return await fts_search(self._db, query, limit=limit)

    async def delete_item(self, item_id: str) -> None:
        async with self._db.write_lock:
            await self._db.execute("DELETE FROM kb_items WHERE item_id = ?", (item_id,))

    async def list_items(
        self,
        tags: list[str] | None = None,
        source_type: KBSourceType | None = None,
        limit: int = 100,
    ) -> list[KBItem]:
        sql = "SELECT * FROM kb_items WHERE 1=1"
        params: list[Any] = []

        if source_type is not None:
            sql += " AND source_type = ?"
            params.append(source_type.value)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = await self._db.fetchall(sql, tuple(params))
        items = [_row_to_item(r) for r in rows]

        # Post-filter by tags (OR logic — item must have at least one matching tag)
        if tags:
            items = [i for i in items if any(t in i.tags for t in tags)]

        return items

    async def export_all(self) -> Path:
        """Export all items to a JSONL file in kb_exports_dir."""
        items = await self.list_items(limit=100_000)
        exports_dir = self._pr.kb_exports_dir
        dest = default_export_path(exports_dir, fmt="jsonl")
        return export_jsonl(items, dest)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _get_by_hash(self, content_hash: str) -> KBItem | None:
        row = await self._db.fetchone(
            "SELECT * FROM kb_items WHERE content_hash = ?", (content_hash,)
        )
        return _row_to_item(row) if row else None


# ── Row helpers ────────────────────────────────────────────────────────────────


def _item_to_row(item: KBItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "title": item.title,
        "content": item.content,
        "source_type": item.source_type.value,
        "source_session_id": item.source_session_id,
        "source_run_id": item.source_run_id,
        "tags": json.dumps(item.tags),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "content_hash": item.content_hash,
        "file_path": item.file_path,
    }
