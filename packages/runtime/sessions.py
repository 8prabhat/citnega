"""SessionManager — lifecycle operations for sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
from citnega.packages.shared.errors import SessionNotFoundError
from citnega.packages.storage.repositories.session_repo import SessionRepository


class SessionManager:
    """Thin facade over SessionRepository for session lifecycle."""

    def __init__(self, session_repo: SessionRepository) -> None:
        self._repo = session_repo

    async def create(self, config: SessionConfig) -> Session:
        now = datetime.now(tz=timezone.utc)
        session = Session(
            config=config,
            created_at=now,
            last_active_at=now,
        )
        await self._repo.save(session)
        runtime_logger.info(
            "session_created",
            session_id=config.session_id,
            name=config.name,
            framework=config.framework,
        )
        return session

    async def get(self, session_id: str) -> Session:
        session = await self._repo.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found.")
        return session

    async def touch(self, session_id: str) -> Session:
        """Update last_active_at and increment run_count."""
        session = await self.get(session_id)
        updated = session.model_copy(
            update={
                "last_active_at": datetime.now(tz=timezone.utc),
                "run_count": session.run_count + 1,
                "state": SessionState.RUNNING,
            }
        )
        await self._repo.save(updated)
        return updated

    async def set_idle(self, session_id: str) -> None:
        session = await self.get(session_id)
        updated = session.model_copy(update={"state": SessionState.IDLE})
        await self._repo.save(updated)

    async def set_error(self, session_id: str) -> None:
        session = await self.get(session_id)
        updated = session.model_copy(update={"state": SessionState.ERROR})
        await self._repo.save(updated)

    async def delete(self, session_id: str) -> None:
        await self._repo.delete(session_id)
        runtime_logger.info("session_deleted", session_id=session_id)

    async def list_all(self) -> list[Session]:
        return await self._repo.list()
