"""
KB retrieval — FTS5 BM25 search with tag and session filters.

SQLite FTS5 BM25 scores are negative (lower = better match).
We normalise to a 0–1 float where 1.0 = best match.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.models.kb import KBItem, KBSearchResult, KBSourceType

if TYPE_CHECKING:
    from citnega.packages.storage.database import DatabaseFactory


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def _row_to_item(row: dict[str, Any]) -> KBItem:
    return KBItem(
        item_id=row["item_id"],
        title=row["title"],
        content=row["content"],
        source_type=KBSourceType(row["source_type"]),
        source_session_id=row.get("source_session_id"),
        source_run_id=row.get("source_run_id"),
        tags=json.loads(row["tags"] or "[]"),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        content_hash=row["content_hash"],
        file_path=row.get("file_path"),
    )


def _snippet(content: str, max_chars: int = 120) -> str:
    """Return a truncated excerpt of content."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars].rsplit(" ", 1)[0] + "…"


async def fts_search(
    db: DatabaseFactory,
    query: str,
    *,
    limit: int = 10,
    tags: list[str] | None = None,
    session_id: str | None = None,
) -> list[KBSearchResult]:
    """
    Full-text search over kb_fts using FTS5 BM25 ranking.

    Joins results back to kb_items to retrieve full metadata.
    Optional filters: ``tags`` (any match) and ``session_id``.
    """
    if not query.strip():
        return []

    # Escape FTS5 special characters
    safe_query = _escape_fts5(query)

    # Base FTS query — bm25() score is negative (lower = better)
    sql = """
        SELECT
            k.item_id, k.title, k.content, k.source_type,
            k.source_session_id, k.source_run_id, k.tags,
            k.created_at, k.updated_at, k.content_hash, k.file_path,
            bm25(kb_fts) AS score
        FROM kb_fts
        JOIN kb_items k USING (item_id)
        WHERE kb_fts MATCH ?
    """
    params: list[Any] = [safe_query]

    if session_id:
        sql += " AND k.source_session_id = ?"
        params.append(session_id)

    sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    rows = await db.fetchall(sql, tuple(params))

    results: list[KBSearchResult] = []
    # Normalise scores: most negative raw → highest normalised
    if rows:
        raw_scores = [r["score"] for r in rows]
        min_score = min(raw_scores)
        max_score = max(raw_scores)
        score_range = max_score - min_score if max_score != min_score else 1.0

        for row in rows:
            item = _row_to_item(row)
            # Optional tag filter (post-filter — FTS doesn't index tags as structured data)
            if tags:
                item_tags = item.tags
                if not any(t in item_tags for t in tags):
                    continue
            # Normalise: best (most negative) → 1.0, worst → 0.0
            norm_score = 1.0 - (row["score"] - min_score) / score_range
            results.append(
                KBSearchResult(
                    item=item,
                    score=round(norm_score, 4),
                    snippet=_snippet(item.content),
                )
            )

    return results


def _escape_fts5(query: str) -> str:
    """
    Sanitise a natural-language query for FTS5 MATCH.

    - Strips punctuation that FTS5 treats as syntax (?, !, ^, *, etc.)
    - Joins remaining words with OR so that partial matches score the document
      (FTS5 uses AND by default, which fails for conversational queries like
      "What is the speed of light?" where "What" is not in the indexed content).
    """
    import re

    # Strip non-word characters except spaces
    words = re.sub(r"[^\w\s]", " ", query, flags=re.UNICODE).split()
    if not words:
        return '""'
    # Single word — pass through directly
    if len(words) == 1:
        return words[0]
    # Multi-word — use OR so any matching term retrieves the document
    return " OR ".join(words)
