"""SessionManager — lifecycle operations for sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState
from citnega.packages.shared.errors import InvalidConfigError, SessionNotFoundError

if TYPE_CHECKING:
    from citnega.packages.storage.repositories.session_repo import SessionRepository

# Frameworks that should never appear in a saved session in production.
# Any session loaded with one of these values is silently migrated to the
# configured default framework.
_DEPRECATED_FRAMEWORKS: frozenset[str] = frozenset({"stub"})


class SessionManager:
    """Thin facade over SessionRepository for session lifecycle."""

    def __init__(
        self,
        session_repo: SessionRepository,
        default_framework: str = "adk",
        strict_framework_validation: bool = False,
        active_frameworks: frozenset[str] | None = None,
    ) -> None:
        self._repo = session_repo
        self._default_framework = default_framework
        self._strict_framework_validation = strict_framework_validation
        # Frameworks accepted without error when strict validation is on.
        self._active_frameworks: frozenset[str] = (
            active_frameworks if active_frameworks is not None else frozenset({default_framework})
        )

    async def _migrate_if_needed(self, session: Session) -> Session:
        """
        If the session was created with a deprecated framework, transparently
        update it to the current configured default and persist the change.
        """
        if session.config.framework not in _DEPRECATED_FRAMEWORKS:
            return session

        new_config = session.config.model_copy(
            update={"framework": self._default_framework}
        )
        migrated = session.model_copy(update={"config": new_config})
        await self._repo.save(migrated)
        runtime_logger.warning(
            "session_framework_migrated",
            session_id=session.config.session_id,
            old_framework=session.config.framework,
            new_framework=self._default_framework,
        )
        return migrated

    async def create(self, config: SessionConfig) -> Session:
        if (
            self._strict_framework_validation
            and config.framework not in self._active_frameworks
            and config.framework not in _DEPRECATED_FRAMEWORKS
        ):
            raise InvalidConfigError(
                f"Framework {config.framework!r} is not registered with the active adapter. "
                f"Active frameworks: {sorted(self._active_frameworks)}. "
                "Set strict_framework_validation=false to disable this check."
            )
        now = datetime.now(tz=UTC)
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
        return await self._migrate_if_needed(session)

    async def touch(self, session_id: str) -> Session:
        """Update last_active_at and increment run_count."""
        session = await self.get(session_id)
        updated = session.model_copy(
            update={
                "last_active_at": datetime.now(tz=UTC),
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

    async def save(self, session: Session) -> None:
        await self._repo.save(session)

    async def delete(self, session_id: str) -> None:
        await self._repo.delete(session_id)
        runtime_logger.info("session_deleted", session_id=session_id)

    async def list_all(self) -> list[Session]:
        sessions = await self._repo.list()
        return [await self._migrate_if_needed(s) for s in sessions]
