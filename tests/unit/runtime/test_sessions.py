"""Unit tests for SessionManager framework migration (FR-CONF-002)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.protocol.models.sessions import Session, SessionConfig
from citnega.packages.runtime.sessions import _DEPRECATED_FRAMEWORKS, SessionManager


def _make_session(framework: str, session_id: str = "s1") -> Session:
    config = SessionConfig(
        session_id=session_id,
        name="test",
        framework=framework,
        default_model_id="model-x",
        max_context_tokens=8192,
    )
    return Session(
        config=config,
        created_at=datetime.now(tz=UTC),
        last_active_at=datetime.now(tz=UTC),
    )


def _make_manager(sessions: list[Session], default_framework: str = "adk") -> SessionManager:
    repo = MagicMock()
    by_id = {s.config.session_id: s for s in sessions}
    repo.get = AsyncMock(side_effect=lambda sid: by_id.get(sid))
    repo.list = AsyncMock(return_value=list(sessions))
    repo.save = AsyncMock()
    mgr = SessionManager(repo, default_framework=default_framework)
    return mgr


class TestDeprecatedFrameworksSet:
    def test_stub_is_deprecated(self) -> None:
        assert "stub" in _DEPRECATED_FRAMEWORKS

    def test_production_frameworks_not_deprecated(self) -> None:
        for fw in ("adk", "langgraph", "crewai", "direct"):
            assert fw not in _DEPRECATED_FRAMEWORKS


class TestSessionMigrationOnGet:
    @pytest.mark.asyncio
    async def test_stub_session_migrated_to_default(self) -> None:
        session = _make_session("stub")
        mgr = _make_manager([session], default_framework="adk")

        result = await mgr.get("s1")

        assert result.config.framework == "adk"

    @pytest.mark.asyncio
    async def test_migration_persisted(self) -> None:
        session = _make_session("stub")
        repo = MagicMock()
        repo.get = AsyncMock(return_value=session)
        repo.save = AsyncMock()
        mgr = SessionManager(repo, default_framework="langgraph")

        await mgr.get("s1")

        repo.save.assert_called_once()
        saved: Session = repo.save.call_args[0][0]
        assert saved.config.framework == "langgraph"

    @pytest.mark.asyncio
    async def test_non_deprecated_framework_not_migrated(self) -> None:
        session = _make_session("adk")
        repo = MagicMock()
        repo.get = AsyncMock(return_value=session)
        repo.save = AsyncMock()
        mgr = SessionManager(repo, default_framework="langgraph")

        result = await mgr.get("s1")

        assert result.config.framework == "adk"
        repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_crewai_session_not_migrated(self) -> None:
        session = _make_session("crewai")
        mgr = _make_manager([session], default_framework="adk")
        result = await mgr.get("s1")
        assert result.config.framework == "crewai"


class TestSessionMigrationOnListAll:
    @pytest.mark.asyncio
    async def test_stub_sessions_migrated_in_list(self) -> None:
        sessions = [
            _make_session("stub", "s1"),
            _make_session("adk", "s2"),
            _make_session("stub", "s3"),
        ]
        mgr = _make_manager(sessions, default_framework="adk")

        result = await mgr.list_all()

        frameworks = {s.config.session_id: s.config.framework for s in result}
        assert frameworks["s1"] == "adk"
        assert frameworks["s2"] == "adk"
        assert frameworks["s3"] == "adk"

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        mgr = _make_manager([])
        result = await mgr.list_all()
        assert result == []


class TestSessionManagerDefaultFramework:
    def test_default_framework_defaults_to_adk(self) -> None:
        repo = MagicMock()
        mgr = SessionManager(repo)
        assert mgr._default_framework == "adk"

    def test_custom_default_framework_stored(self) -> None:
        repo = MagicMock()
        mgr = SessionManager(repo, default_framework="crewai")
        assert mgr._default_framework == "crewai"
