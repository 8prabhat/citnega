"""
Integration tests for KnowledgeStore against a real SQLite DB.

Creates the kb_items + kb_fts tables inline so tests don't depend on
Alembic migrations being applied.

Coverage:
  1. add_item → get_item round-trip
  2. FTS search returns relevant results
  3. Content-hash deduplication
  4. delete_item removes from kb_items and FTS
  5. list_items with source_type + tags filters
  6. export_all produces a JSONL file
  7. Multi-session isolation (search by source_session_id)
  8. KBRetrievalHandler enriches ContextObject with KB snippets
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from citnega.packages.kb.ingestion import content_hash
from citnega.packages.kb.store import KnowledgeStore
from citnega.packages.protocol.models.kb import KBItem, KBSourceType
from citnega.packages.storage.database import DatabaseFactory
from citnega.packages.storage.path_resolver import PathResolver


# ---------------------------------------------------------------------------
# Schema DDL (matches migration 0001_initial.py)
# ---------------------------------------------------------------------------

_KB_DDL = [
    """CREATE TABLE IF NOT EXISTS kb_items (
        item_id             TEXT PRIMARY KEY,
        title               TEXT NOT NULL,
        content             TEXT NOT NULL,
        source_type         TEXT NOT NULL,
        source_session_id   TEXT,
        source_run_id       TEXT,
        tags                TEXT NOT NULL DEFAULT '[]',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        content_hash        TEXT NOT NULL,
        file_path           TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kb_content_hash ON kb_items(content_hash)",
    """CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
        item_id UNINDEXED,
        title,
        content,
        tags,
        tokenize = 'porter unicode61'
    )""",
    """CREATE TRIGGER IF NOT EXISTS kb_items_ai
    AFTER INSERT ON kb_items
    BEGIN
        INSERT INTO kb_fts(item_id, title, content, tags)
        VALUES (NEW.item_id, NEW.title, NEW.content, NEW.tags);
    END""",
    """CREATE TRIGGER IF NOT EXISTS kb_items_ad
    AFTER DELETE ON kb_items
    BEGIN
        DELETE FROM kb_fts WHERE item_id = OLD.item_id;
    END""",
    """CREATE TRIGGER IF NOT EXISTS kb_items_au
    AFTER UPDATE ON kb_items
    BEGIN
        DELETE FROM kb_fts WHERE item_id = OLD.item_id;
        INSERT INTO kb_fts(item_id, title, content, tags)
        VALUES (NEW.item_id, NEW.title, NEW.content, NEW.tags);
    END""",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path: Path):
    db_path = tmp_path / "kb_test.db"
    db      = DatabaseFactory(db_path)
    pr      = PathResolver(app_home=tmp_path / "app")

    async def _setup():
        await db.connect()
        for ddl in _KB_DDL:
            async with db.write_lock:
                await db.execute(ddl)
        return KnowledgeStore(db, pr)

    ks = asyncio.run(_setup())

    yield ks, db

    asyncio.run(db.disconnect())


def _item(
    content: str,
    title: str = "Test",
    source_type: KBSourceType = KBSourceType.NOTE,
    tags: list[str] | None = None,
    session_id: str | None = None,
) -> KBItem:
    now = datetime.now(tz=timezone.utc)
    return KBItem(
        item_id=str(uuid.uuid4()),
        title=title,
        content=content,
        source_type=source_type,
        source_session_id=session_id,
        tags=tags or [],
        created_at=now,
        updated_at=now,
        content_hash=content_hash(content),
    )


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAddAndGet:
    def test_round_trip(self, store) -> None:
        ks, _ = store
        item = _item("Python is a programming language.")
        run(ks.add_item(item))
        fetched = run(ks.get_item(item.item_id))
        assert fetched is not None
        assert fetched.item_id    == item.item_id
        assert fetched.content    == item.content
        assert fetched.content_hash == item.content_hash

    def test_get_missing_returns_none(self, store) -> None:
        ks, _ = store
        assert run(ks.get_item("no-such-id")) is None


class TestDeduplication:
    def test_duplicate_content_hash_not_inserted(self, store) -> None:
        ks, _ = store
        content = "Deduplicated content."
        item1 = _item(content, title="First")
        item2 = _item(content, title="Second")  # same content → same hash

        run(ks.add_item(item1))
        returned = run(ks.add_item(item2))  # should return item1

        # Only one row in the DB
        all_items = run(ks.list_items())
        assert len(all_items) == 1
        assert all_items[0].item_id == item1.item_id
        assert returned.item_id == item1.item_id

    def test_different_content_both_inserted(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("content A")))
        run(ks.add_item(_item("content B")))
        all_items = run(ks.list_items())
        assert len(all_items) == 2


class TestSearch:
    def test_search_returns_relevant_result(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("Python is great for data science.", title="Python")))
        run(ks.add_item(_item("JavaScript is used for web frontends.", title="JS")))

        results = run(ks.search("Python data science"))
        assert len(results) >= 1
        titles = [r.item.title for r in results]
        assert "Python" in titles

    def test_search_empty_query_returns_empty(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("some content")))
        results = run(ks.search(""))
        assert results == []

    def test_search_no_matches_returns_empty(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("Python is great")))
        results = run(ks.search("XYZZY_NOT_A_REAL_WORD_12345"))
        assert results == []

    def test_search_result_has_score_and_snippet(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("Machine learning with Python.", title="ML")))
        results = run(ks.search("machine learning"))
        assert len(results) >= 1
        r = results[0]
        assert 0.0 <= r.score <= 1.0
        assert r.snippet

    def test_top_result_most_relevant(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("Python Python Python", title="Heavy Python")))
        run(ks.add_item(_item("Just one Python mention here.", title="Light Python")))
        results = run(ks.search("Python", limit=2))
        assert results[0].score >= results[1].score


class TestDelete:
    def test_delete_removes_item(self, store) -> None:
        ks, _ = store
        item = _item("Temporary content to delete.")
        run(ks.add_item(item))
        run(ks.delete_item(item.item_id))
        assert run(ks.get_item(item.item_id)) is None

    def test_delete_removes_from_fts(self, store) -> None:
        ks, _ = store
        item = _item("Unique deletable content zXqW.")
        run(ks.add_item(item))
        run(ks.delete_item(item.item_id))
        # FTS search should not find it
        results = run(ks.search("zXqW"))
        item_ids = [r.item.item_id for r in results]
        assert item.item_id not in item_ids


class TestListItems:
    def test_list_all(self, store) -> None:
        ks, _ = store
        for i in range(3):
            run(ks.add_item(_item(f"content {i}")))
        items = run(ks.list_items())
        assert len(items) == 3

    def test_list_by_source_type(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("note content", source_type=KBSourceType.NOTE)))
        run(ks.add_item(_item("doc content",  source_type=KBSourceType.DOCUMENT)))
        notes = run(ks.list_items(source_type=KBSourceType.NOTE))
        assert len(notes) == 1
        assert notes[0].source_type == KBSourceType.NOTE

    def test_list_by_tag(self, store) -> None:
        ks, _ = store
        run(ks.add_item(_item("tagged item", tags=["python", "ml"])))
        run(ks.add_item(_item("other item",  tags=["web"])))
        python_items = run(ks.list_items(tags=["python"]))
        assert len(python_items) == 1

    def test_limit_respected(self, store) -> None:
        ks, _ = store
        for i in range(10):
            run(ks.add_item(_item(f"item {i}")))
        items = run(ks.list_items(limit=3))
        assert len(items) <= 3


class TestExportAll:
    def test_export_creates_jsonl(self, store, tmp_path: Path) -> None:
        ks, _ = store
        run(ks.add_item(_item("export test content")))
        path = run(ks.export_all())
        assert path.exists()
        assert path.suffix == ".jsonl"
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_export_empty_db_creates_empty_file(self, store) -> None:
        ks, _ = store
        path = run(ks.export_all())
        assert path.exists()
        assert path.read_text() == ""


class TestMultiSessionIsolation:
    def test_search_scoped_to_session(self, store) -> None:
        ks, _ = store
        sess_a = str(uuid.uuid4())
        sess_b = str(uuid.uuid4())
        run(ks.add_item(_item("Python pandas session A", session_id=sess_a)))
        run(ks.add_item(_item("Python pandas session B", session_id=sess_b)))

        from citnega.packages.kb.retrieval import fts_search
        from citnega.packages.storage.database import DatabaseFactory

        _, db = store

        results_a = asyncio.run(fts_search(db, "Python pandas", session_id=sess_a))
        assert all(r.item.source_session_id == sess_a for r in results_a)

    def test_items_from_different_sessions_coexist(self, store) -> None:
        ks, _ = store
        sess_a = str(uuid.uuid4())
        sess_b = str(uuid.uuid4())
        run(ks.add_item(_item("content A", session_id=sess_a)))
        run(ks.add_item(_item("content B", session_id=sess_b)))
        all_items = run(ks.list_items())
        assert len(all_items) == 2


class TestKBRetrievalHandler:
    def test_enriches_context_with_kb_results(self, store) -> None:
        from datetime import datetime, timezone
        from citnega.packages.kb.store import KnowledgeStore
        from citnega.packages.protocol.models.context import ContextObject
        from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
        from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler

        ks, _ = store
        run(ks.add_item(_item("The speed of light is 299,792,458 m/s.", title="Physics")))

        handler = KBRetrievalHandler(kb_store=ks, retrieve_limit=3)

        now = datetime.now(tz=timezone.utc)
        session = Session(
            config=SessionConfig(
                session_id="s1",
                name="test",
                framework="stub",
                default_model_id="",
                kb_enabled=True,
            ),
            created_at=now,
            last_active_at=now,
            state=SessionState.IDLE,
        )
        context = ContextObject(
            session_id="s1",
            run_id="r1",
            user_input="What is the speed of light?",
            assembled_at=now,
            budget_remaining=8192,
        )

        enriched = run(handler.enrich(context, session))
        kb_sources = [s for s in enriched.sources if s.source_type == "kb"]
        assert len(kb_sources) == 1
        assert "299,792,458" in kb_sources[0].content

    def test_no_op_when_kb_disabled(self, store) -> None:
        from datetime import datetime, timezone
        from citnega.packages.protocol.models.context import ContextObject
        from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
        from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler

        ks, _ = store
        run(ks.add_item(_item("something searchable")))

        handler = KBRetrievalHandler(kb_store=ks)

        now = datetime.now(tz=timezone.utc)
        session = Session(
            config=SessionConfig(
                session_id="s2",
                name="test",
                framework="stub",
                default_model_id="",
                kb_enabled=False,   # KB disabled
            ),
            created_at=now,
            last_active_at=now,
            state=SessionState.IDLE,
        )
        context = ContextObject(
            session_id="s2",
            run_id="r2",
            user_input="something searchable",
            assembled_at=now,
            budget_remaining=8192,
        )
        enriched = run(handler.enrich(context, session))
        kb_sources = [s for s in enriched.sources if s.source_type == "kb"]
        assert len(kb_sources) == 0

    def test_no_op_when_store_is_none(self) -> None:
        from datetime import datetime, timezone
        from citnega.packages.protocol.models.context import ContextObject
        from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
        from citnega.packages.runtime.context.handlers.kb_retrieval import KBRetrievalHandler

        handler = KBRetrievalHandler(kb_store=None)
        now = datetime.now(tz=timezone.utc)
        session = Session(
            config=SessionConfig(
                session_id="s3",
                name="test",
                framework="stub",
                default_model_id="",
                kb_enabled=True,
            ),
            created_at=now,
            last_active_at=now,
            state=SessionState.IDLE,
        )
        context = ContextObject(
            session_id="s3",
            run_id="r3",
            user_input="query",
            assembled_at=now,
            budget_remaining=8192,
        )
        result = run(handler.enrich(context, session))
        assert result is context   # unchanged
