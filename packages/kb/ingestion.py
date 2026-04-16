"""
KB ingestion — text chunking and content-hash deduplication.

Chunking strategy:
  1. Split on double-newlines (paragraph boundaries).
  2. If a paragraph exceeds ``max_tokens``, split by single newline,
     then by sentence boundary (". "), accumulating until the budget
     is reached.
  3. Estimate tokens as len(text) // 4 (same as TokenBudgetHandler).

Deduplication:
  The caller checks ``KBIngestion.content_hash(text)`` against stored
  hashes before inserting.  The store itself enforces uniqueness via
  ``ON CONFLICT(content_hash) DO NOTHING``.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
from typing import TYPE_CHECKING
import uuid

from citnega.packages.protocol.models.kb import KBItem, KBSourceType

if TYPE_CHECKING:
    from collections.abc import Iterator

# ── Constants ─────────────────────────────────────────────────────────────────

_DEFAULT_MAX_TOKENS = 512
_CHARS_PER_TOKEN = 4


def _get_default_chunk_tokens() -> int:
    try:
        from citnega.packages.config.loaders import load_settings

        return load_settings().context.kb_chunk_size_tokens
    except Exception:
        return _DEFAULT_MAX_TOKENS


# ── Public helpers ────────────────────────────────────────────────────────────


def content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of *text* (UTF-8 encoded)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    *,
    max_tokens: int | None = None,
) -> list[str]:
    """
    Split *text* into chunks that each fit within *max_tokens*.

    Returns a list of non-empty strings.  Defaults to settings.context.kb_chunk_size_tokens.
    """
    effective_max = max_tokens if max_tokens is not None else _get_default_chunk_tokens()
    max_chars = effective_max * _CHARS_PER_TOKEN
    return list(_do_chunk(text, max_chars))


def _do_chunk(text: str, max_chars: int) -> Iterator[str]:
    paragraphs = re.split(r"\n{2,}", text.strip())
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            yield para
        else:
            # Split paragraph further
            yield from _split_long(para, max_chars)


def _split_long(text: str, max_chars: int) -> Iterator[str]:
    """Split a paragraph that exceeds max_chars at sentence boundaries."""
    sentences = re.split(r"(?<=\. )", text)
    buf = ""
    for sent in sentences:
        if len(buf) + len(sent) <= max_chars:
            buf += sent
        else:
            if buf:
                yield buf.strip()
            # If the sentence itself is too long, split at word boundaries
            if len(sent) > max_chars:
                word_buf = ""
                for w in sent.split():
                    candidate = (word_buf + " " + w).lstrip() if word_buf else w
                    if len(candidate) <= max_chars:
                        word_buf = candidate
                    else:
                        if word_buf:
                            yield word_buf.strip()
                        word_buf = w
                buf = word_buf
            else:
                buf = sent
    if buf.strip():
        yield buf.strip()


# ── Item builder ──────────────────────────────────────────────────────────────


def build_items(
    text: str,
    title: str,
    source_type: KBSourceType = KBSourceType.DOCUMENT,
    *,
    tags: list[str] | None = None,
    source_session_id: str | None = None,
    source_run_id: str | None = None,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[KBItem]:
    """
    Chunk *text* and build a list of :class:`KBItem` objects ready for
    ingestion.  Each chunk gets its own ``item_id`` and ``content_hash``.
    """
    chunks = chunk_text(text, max_tokens=max_tokens)
    now = datetime.now(tz=UTC)
    items: list[KBItem] = []

    for i, chunk in enumerate(chunks):
        chunk_title = title if len(chunks) == 1 else f"{title} [{i + 1}/{len(chunks)}]"
        items.append(
            KBItem(
                item_id=str(uuid.uuid4()),
                title=chunk_title,
                content=chunk,
                source_type=source_type,
                source_session_id=source_session_id,
                source_run_id=source_run_id,
                tags=tags or [],
                created_at=now,
                updated_at=now,
                content_hash=content_hash(chunk),
            )
        )

    return items
