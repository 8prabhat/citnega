"""
CLI bootstrap — thin wrapper around the canonical application bootstrap.

Historically the CLI/TUI had a separate composition root that drifted from
``packages.bootstrap.bootstrap.create_application``.  This module now delegates
directly to the canonical bootstrap so all entrypoints share one wiring path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from citnega.packages.bootstrap.bootstrap import create_application

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from citnega.packages.runtime.app_service import ApplicationService


@asynccontextmanager
async def cli_bootstrap(
    *,
    db_path: Path | None = None,
    app_home: Path | None = None,
    run_migrations: bool = True,
) -> AsyncIterator[ApplicationService]:
    """
    Create an ``ApplicationService`` for CLI and TUI use.

    CLI/TUI always run on the ``direct`` adapter and intentionally skip the
    provider health gate at startup so local/offline workflows still launch.
    """
    async with create_application(
        db_path=db_path,
        app_home=app_home,
        framework="direct",
        run_migrations=run_migrations,
        skip_provider_health_check=True,
    ) as svc:
        yield svc
