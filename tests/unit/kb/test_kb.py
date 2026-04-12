"""Unit tests for KB ingestion, retrieval helpers, and export."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from typing import TYPE_CHECKING
import uuid

from citnega.packages.kb.export import export_jsonl, export_markdown
from citnega.packages.kb.ingestion import build_items, chunk_text, content_hash
from citnega.packages.protocol.models.kb import KBItem, KBSourceType

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = content_hash("hello world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_different_texts_different_hashes(self) -> None:
        assert content_hash("foo") != content_hash("bar")

    def test_sha256_hex(self) -> None:
        expected = hashlib.sha256(b"test").hexdigest()
        assert content_hash("test") == expected


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        chunks = chunk_text("Hello world.", max_tokens=512)
        assert chunks == ["Hello world."]

    def test_empty_text_empty_list(self) -> None:
        assert chunk_text("") == []

    def test_whitespace_only_empty_list(self) -> None:
        assert chunk_text("   \n\n   ") == []

    def test_paragraph_split(self) -> None:
        text = "First paragraph.\n\nSecond paragraph."
        chunks = chunk_text(text, max_tokens=512)
        assert len(chunks) == 2
        assert "First paragraph." in chunks[0]
        assert "Second paragraph." in chunks[1]

    def test_long_text_multiple_chunks(self) -> None:
        # 100 words × ~5 chars each = ~500 chars; max_tokens=32 → max_chars=128
        text = " ".join(["word"] * 100)
        chunks = chunk_text(text, max_tokens=32)
        assert len(chunks) > 1
        # Each chunk must not exceed 32 * 4 = 128 chars
        for chunk in chunks:
            assert len(chunk) <= 128 + 20  # small tolerance for word boundaries

    def test_chunks_cover_all_content(self) -> None:
        words = ["word" + str(i) for i in range(50)]
        text = " ".join(words)
        chunks = chunk_text(text, max_tokens=16)
        rejoined = " ".join(chunks)
        for word in words:
            assert word in rejoined


# ---------------------------------------------------------------------------
# build_items
# ---------------------------------------------------------------------------


class TestBuildItems:
    def test_single_short_text(self) -> None:
        items = build_items("Short.", title="T", source_type=KBSourceType.NOTE)
        assert len(items) == 1
        assert items[0].title == "T"
        assert items[0].source_type == KBSourceType.NOTE

    def test_multiple_chunks_numbered_titles(self) -> None:
        long_text = "sentence. " * 80
        items = build_items(long_text, title="Doc", max_tokens=32)
        assert len(items) > 1
        assert "[1/" in items[0].title
        assert "[2/" in items[1].title

    def test_content_hash_set(self) -> None:
        items = build_items("test content", title="T")
        assert items[0].content_hash == content_hash("test content")

    def test_tags_propagated(self) -> None:
        items = build_items("content", title="T", tags=["tag1", "tag2"])
        assert items[0].tags == ["tag1", "tag2"]

    def test_unique_item_ids(self) -> None:
        long_text = "word " * 200
        items = build_items(long_text, title="T", max_tokens=32)
        ids = [i.item_id for i in items]
        assert len(ids) == len(set(ids))

    def test_source_session_id_propagated(self) -> None:
        items = build_items("x", title="T", source_session_id="sess-1")
        assert items[0].source_session_id == "sess-1"


# ---------------------------------------------------------------------------
# export helpers
# ---------------------------------------------------------------------------


def _make_item(content: str = "test content") -> KBItem:
    now = datetime.now(tz=UTC)
    return KBItem(
        item_id=str(uuid.uuid4()),
        title="Test Item",
        content=content,
        source_type=KBSourceType.NOTE,
        tags=["test"],
        created_at=now,
        updated_at=now,
        content_hash=content_hash(content),
    )


class TestExportJSONL:
    def test_creates_file(self, tmp_path: Path) -> None:
        items = [_make_item(), _make_item("another")]
        dest = tmp_path / "kb.jsonl"
        result = export_jsonl(items, dest)
        assert result == dest
        assert dest.exists()

    def test_one_line_per_item(self, tmp_path: Path) -> None:
        items = [_make_item(), _make_item("b"), _make_item("c")]
        dest = tmp_path / "kb.jsonl"
        export_jsonl(items, dest)
        lines = [ln for ln in dest.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3

    def test_json_parseable(self, tmp_path: Path) -> None:
        import json

        item = _make_item()
        dest = tmp_path / "kb.jsonl"
        export_jsonl([item], dest)
        data = json.loads(dest.read_text().strip())
        assert data["item_id"] == item.item_id
        assert data["content"] == item.content

    def test_empty_list_creates_empty_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "empty.jsonl"
        export_jsonl([], dest)
        assert dest.exists()
        assert dest.read_text() == ""


class TestExportMarkdown:
    def test_creates_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "kb.md"
        export_markdown([_make_item()], dest)
        assert dest.exists()

    def test_contains_title(self, tmp_path: Path) -> None:
        item = _make_item()
        dest = tmp_path / "kb.md"
        export_markdown([item], dest)
        text = dest.read_text()
        assert item.title in text

    def test_contains_content_as_blockquote(self, tmp_path: Path) -> None:
        item = _make_item("unique content string xyz")
        dest = tmp_path / "kb.md"
        export_markdown([item], dest)
        text = dest.read_text()
        assert "> unique content string xyz" in text
