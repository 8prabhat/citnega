"""
DatabaseFactory — single authority for SQLite connection management.

Opens one aiosqlite connection per process, applies WAL PRAGMAs on every
connection, and serialises writes through an asyncio.Lock.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import aiosqlite

from citnega.packages.shared.errors import MigrationError, StorageError

if TYPE_CHECKING:
    from pathlib import Path

_PRAGMAS = [
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
]


class DatabaseFactory:
    """
    Manages a single aiosqlite connection for the process lifetime.

    Usage::

        factory = DatabaseFactory(db_path)
        await factory.connect()
        async with factory.write_lock:
            await factory.execute("INSERT INTO ...")
        await factory.disconnect()
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open connection and apply WAL PRAGMAs. No-op if already connected."""
        if self._conn is not None:
            return
        try:
            self._conn = await aiosqlite.connect(str(self._db_path))
            self._conn.row_factory = aiosqlite.Row
            for pragma in _PRAGMAS:
                await self._conn.execute(pragma)
            await self._conn.commit()
        except Exception as exc:
            raise StorageError(
                f"Failed to open database at {self._db_path}: {exc}",
                original=exc,
            ) from exc

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise StorageError("Database not connected. Call connect() first.")
        return self._conn

    async def execute(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> aiosqlite.Cursor:
        """Execute a statement (write or DDL). Caller must hold write_lock."""
        try:
            if parameters:
                cursor = await self.connection.execute(sql, parameters)
            else:
                cursor = await self.connection.execute(sql)
            await self.connection.commit()
            return cursor
        except Exception as exc:
            raise StorageError(
                f"Database execute failed: {exc}\nSQL: {sql}",
                original=exc,
            ) from exc

    async def fetchall(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as dicts."""
        try:
            if parameters:
                async with self.connection.execute(sql, parameters) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with self.connection.execute(sql) as cursor:
                    rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            raise StorageError(
                f"Database fetchall failed: {exc}\nSQL: {sql}",
                original=exc,
            ) from exc

    async def fetchone(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """Execute a SELECT and return one row as a dict, or None."""
        try:
            if parameters:
                async with self.connection.execute(sql, parameters) as cursor:
                    row = await cursor.fetchone()
            else:
                async with self.connection.execute(sql) as cursor:
                    row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as exc:
            raise StorageError(
                f"Database fetchone failed: {exc}\nSQL: {sql}",
                original=exc,
            ) from exc

    async def run_migrations(self, alembic_ini_path: Path) -> None:
        """
        Run Alembic migrations synchronously (Alembic is not async-aware).

        Closes the async connection first, runs sync migrations, then reconnects.
        """
        await self.disconnect()
        try:
            from alembic import command
            from alembic.config import Config

            cfg = Config(str(alembic_ini_path))
            cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self._db_path}")
            command.upgrade(cfg, "head")
        except Exception as exc:
            raise MigrationError(f"Alembic migration failed: {exc}", original=exc) from exc
        finally:
            await self.connect()
