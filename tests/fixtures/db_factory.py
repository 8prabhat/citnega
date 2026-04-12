"""Shared database fixture — temp SQLite DB with migrations applied."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

from citnega.packages.storage.database import DatabaseFactory
from citnega.packages.storage.path_resolver import PathResolver

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


@pytest_asyncio.fixture
async def tmp_db(tmp_path: Path) -> AsyncGenerator[DatabaseFactory, None]:
    """
    A fresh DatabaseFactory backed by a temp SQLite file with all
    migrations applied. Cleaned up after each test.
    """
    path_resolver = PathResolver(app_home=tmp_path)
    path_resolver.create_all()

    db = DatabaseFactory(path_resolver.db_path)
    await db.connect()

    alembic_ini = path_resolver.alembic_ini_path()
    await db.run_migrations(alembic_ini)

    yield db

    await db.disconnect()
