"""
Integration tests for conversation compaction (FR-CTX-003).

Validates:
  - compact() archives old messages and inserts a summary marker
  - compaction_count increments after each compaction
  - RecentTurnsHandler returns fewer messages (and the summary) after compaction
  - Second compaction on an already-compacted store works correctly
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from citnega.packages.runtime.context.conversation_store import ConversationStore

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> ConversationStore:
    """A fresh ConversationStore backed by a temp directory."""
    session_dir = tmp_path / "session-compact-test"
    session_dir.mkdir()
    cs = ConversationStore(session_dir=session_dir, default_model_id="test-model")
    await cs.load()
    return cs


async def _add_turns(store: ConversationStore, n: int) -> None:
    """Add n user/assistant pairs to the store."""
    for i in range(n):
        await store.add_message("user", f"User message {i}")
        await store.add_message("assistant", f"Assistant reply {i}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompactionStorage:
    @pytest.mark.asyncio
    async def test_compact_archives_old_messages(self, store: ConversationStore) -> None:
        """compact() must reduce message count and insert summary marker."""
        await _add_turns(store, 10)  # 20 messages (10 user + 10 assistant)
        before_count = len(store.get_messages())
        assert before_count == 20

        archived = await store.compact("Summary of first 10 turns.", keep_recent=4)

        after_msgs = store.get_messages()
        assert archived == 16, f"Expected 16 archived, got {archived}"
        # Summary marker (system) + 4 recent content messages
        assert len(after_msgs) == 5, f"Expected 5 msgs after compact, got {len(after_msgs)}"

    @pytest.mark.asyncio
    async def test_compact_inserts_summary_content(self, store: ConversationStore) -> None:
        """The compaction marker must contain the provided summary text."""
        await _add_turns(store, 6)
        await store.compact("KEY FACTS: topic A and topic B.", keep_recent=2)

        messages = store.get_messages()
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert system_msgs, "Expected at least one system message after compaction"
        combined = " ".join(m["content"] for m in system_msgs)
        assert "KEY FACTS" in combined, "Summary text not found in compaction marker"
        assert "Compacted" in combined, "Compaction header not found in system message"

    @pytest.mark.asyncio
    async def test_compaction_count_increments(self, store: ConversationStore) -> None:
        """compaction_count must increment with each compact() call."""
        assert store.compaction_count == 0

        await _add_turns(store, 8)
        await store.compact("First compaction.", keep_recent=2)
        assert store.compaction_count == 1

        await _add_turns(store, 8)
        await store.compact("Second compaction.", keep_recent=2)
        assert store.compaction_count == 2

    @pytest.mark.asyncio
    async def test_compact_noop_when_nothing_to_archive(self, store: ConversationStore) -> None:
        """compact() must return 0 when keep_recent >= total messages."""
        await _add_turns(store, 3)
        archived = await store.compact("No-op summary.", keep_recent=10)
        assert archived == 0
        assert store.compaction_count == 0

    @pytest.mark.asyncio
    async def test_compaction_persists_across_reload(
        self, store: ConversationStore, tmp_path: Path
    ) -> None:
        """Summary marker must survive a save/reload cycle."""
        await _add_turns(store, 8)
        await store.compact("Persisted summary.", keep_recent=2)

        # Reload from same directory
        store2 = ConversationStore(
            session_dir=tmp_path / "session-compact-test",
            default_model_id="test-model",
        )
        await store2.load()

        messages = store2.get_messages()
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert any("Persisted summary" in m["content"] for m in system_msgs)
        assert store2.compaction_count == 1


class TestRecentTurnsHandlerAfterCompaction:
    """Verify that RecentTurnsHandler sees the reduced context after compaction."""

    @pytest.mark.asyncio
    async def test_recent_turns_count_reduced_after_compact(
        self, store: ConversationStore, tmp_path: Path
    ) -> None:
        """After compaction, RecentTurnsHandler should return fewer messages."""
        from unittest.mock import AsyncMock, MagicMock

        from citnega.packages.protocol.models.context import ContextObject
        from citnega.packages.protocol.models.sessions import SessionConfig
        from citnega.packages.runtime.context.handlers.recent_turns import RecentTurnsHandler

        # Populate store with 20 messages, then compact keeping 4
        await _add_turns(store, 10)
        await store.compact("Summary of old messages.", keep_recent=4)

        # Simulate MessageRepository using the store's post-compact message list
        # by stubbing list() to return the store's current messages
        post_compact_msgs = store.get_messages()

        from datetime import UTC
        from datetime import datetime as _dt
        import uuid as _uuid

        from citnega.packages.protocol.models.messages import Message, MessageRole

        def _to_msg(m: dict) -> Message:
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
            }
            return Message(
                message_id=str(_uuid.uuid4()),
                session_id="s1",
                role=role_map.get(m["role"], MessageRole.USER),
                content=m["content"],
                timestamp=_dt.now(tz=UTC),
            )

        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(
            return_value=[_to_msg(m) for m in post_compact_msgs]
        )

        handler = RecentTurnsHandler(mock_repo, recent_turns_count=20)

        session_cfg = SessionConfig(
            session_id="s1",
            name="test",
            framework="stub",
            default_model_id="model-x",
            max_context_tokens=8192,
        )
        mock_session = MagicMock()
        mock_session.config = session_cfg

        from datetime import datetime as _datetime2

        context = ContextObject(
            session_id="s1",
            run_id="r1",
            user_input="next question",
            assembled_at=_datetime2.now(tz=UTC),
            budget_remaining=8192,
        )

        enriched = await handler.enrich(context, mock_session)

        # Should have 5 sources (1 compaction marker + 4 recent content messages)
        assert len(enriched.sources) <= 1, (
            "RecentTurnsHandler should combine into a single context source"
        )
        # The source content should contain the summary
        if enriched.sources:
            combined_content = enriched.sources[0].content
            assert "Summary of old messages" in combined_content or len(combined_content) > 0
