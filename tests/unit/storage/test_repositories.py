"""Integration-style unit tests for all repositories (uses real SQLite)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
import uuid

import pytest

from citnega.packages.protocol.models.kb import KBItem, KBSourceType
from citnega.packages.protocol.models.runs import RunState, RunSummary
from citnega.packages.protocol.models.sessions import Session, SessionConfig
from citnega.packages.storage.repositories import (
    KBRepository,
    RunRepository,
    SessionRepository,
)

if TYPE_CHECKING:
    from citnega.packages.storage.database import DatabaseFactory


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Session Repo ───────────────────────────────────────────────────────────────


class TestSessionRepository:
    @pytest.mark.asyncio
    async def test_save_and_get(self, tmp_db: DatabaseFactory) -> None:
        repo = SessionRepository(tmp_db)
        cfg = SessionConfig(
            session_id=_uuid(),
            name="Test",
            framework="adk",
            default_model_id="gemma3",
        )
        session = Session(config=cfg, created_at=_now(), last_active_at=_now())
        await repo.save(session)

        loaded = await repo.get(cfg.session_id)
        assert loaded is not None
        assert loaded.config.session_id == cfg.session_id
        assert loaded.config.framework == "adk"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, tmp_db: DatabaseFactory) -> None:
        repo = SessionRepository(tmp_db)
        assert await repo.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list(self, tmp_db: DatabaseFactory) -> None:
        repo = SessionRepository(tmp_db)
        for i in range(3):
            cfg = SessionConfig(
                session_id=_uuid(),
                name=f"S{i}",
                framework="adk",
                default_model_id="gemma3",
            )
            s = Session(config=cfg, created_at=_now(), last_active_at=_now())
            await repo.save(s)
        sessions = await repo.list(limit=10)
        assert len(sessions) == 3

    @pytest.mark.asyncio
    async def test_delete(self, tmp_db: DatabaseFactory) -> None:
        repo = SessionRepository(tmp_db)
        cfg = SessionConfig(
            session_id=_uuid(),
            name="ToDelete",
            framework="langgraph",
            default_model_id="gpt-4o",
        )
        s = Session(config=cfg, created_at=_now(), last_active_at=_now())
        await repo.save(s)
        await repo.delete(cfg.session_id)
        assert await repo.get(cfg.session_id) is None


# ── Run Repo ───────────────────────────────────────────────────────────────────


class TestRunRepository:
    @pytest.fixture
    async def saved_session_id(self, tmp_db: DatabaseFactory) -> str:
        repo = SessionRepository(tmp_db)
        sid = _uuid()
        cfg = SessionConfig(session_id=sid, name="S", framework="adk", default_model_id="m")
        s = Session(config=cfg, created_at=_now(), last_active_at=_now())
        await repo.save(s)
        return sid

    @pytest.mark.asyncio
    async def test_save_and_get(self, tmp_db: DatabaseFactory, saved_session_id: str) -> None:
        repo = RunRepository(tmp_db)
        run = RunSummary(
            run_id=_uuid(),
            session_id=saved_session_id,
            state=RunState.PENDING,
            started_at=_now(),
        )
        await repo.save(run)
        loaded = await repo.get(run.run_id)
        assert loaded is not None
        assert loaded.state == RunState.PENDING

    @pytest.mark.asyncio
    async def test_list_by_session(self, tmp_db: DatabaseFactory, saved_session_id: str) -> None:
        repo = RunRepository(tmp_db)
        for _ in range(2):
            run = RunSummary(
                run_id=_uuid(),
                session_id=saved_session_id,
                state=RunState.COMPLETED,
                started_at=_now(),
            )
            await repo.save(run)
        runs = await repo.list(session_id=saved_session_id)
        assert len(runs) == 2


# ── KB Repo ────────────────────────────────────────────────────────────────────


class TestKBRepository:
    @pytest.mark.asyncio
    async def test_save_and_get(self, tmp_db: DatabaseFactory) -> None:
        repo = KBRepository(tmp_db)
        item = KBItem(
            item_id=_uuid(),
            title="Test Item",
            content="Content about climate change.",
            source_type=KBSourceType.NOTE,
            created_at=_now(),
            updated_at=_now(),
            content_hash="abc123",
        )
        await repo.save(item)
        loaded = await repo.get(item.item_id)
        assert loaded is not None
        assert loaded.title == "Test Item"

    @pytest.mark.asyncio
    async def test_search_fts(self, tmp_db: DatabaseFactory) -> None:
        repo = KBRepository(tmp_db)
        item = KBItem(
            item_id=_uuid(),
            title="Climate Risks",
            content="Southeast Asia faces severe flooding and drought.",
            source_type=KBSourceType.DOCUMENT,
            created_at=_now(),
            updated_at=_now(),
            content_hash=_uuid(),
        )
        await repo.save(item)
        results = await repo.search("flooding drought", limit=5)
        assert len(results) >= 1
        assert results[0].item.item_id == item.item_id

    @pytest.mark.asyncio
    async def test_delete(self, tmp_db: DatabaseFactory) -> None:
        repo = KBRepository(tmp_db)
        item = KBItem(
            item_id=_uuid(),
            title="Del",
            content="x",
            source_type=KBSourceType.NOTE,
            created_at=_now(),
            updated_at=_now(),
            content_hash="h1",
        )
        await repo.save(item)
        await repo.delete(item.item_id)
        assert await repo.get(item.item_id) is None
