"""citnega migrate — run Alembic database migrations."""

from __future__ import annotations

import typer

from citnega.apps.cli._async import run_async
from citnega.packages.storage.path_resolver import PathResolver

app = typer.Typer(help="Run database migrations.")


@app.command("migrate")
@run_async
async def migrate_command(
    revision: str = typer.Option("head", "--revision", "-r", help="Target revision."),
) -> None:
    """
    Run Alembic migrations up to *revision* (default: head).

    Creates the database file if it does not yet exist.
    """
    from citnega.packages.storage.database import DatabaseFactory

    resolver = PathResolver()
    db_path = resolver.db_path
    alembic_ini = resolver.alembic_ini_path()

    typer.echo(f"Database: {db_path}")
    typer.echo(f"Alembic:  {alembic_ini}")

    if not alembic_ini.exists():
        typer.echo(
            f"alembic.ini not found at {alembic_ini}.  "
            "Run from the repository root or provide a custom path.",
            err=True,
        )
        raise typer.Exit(code=1)

    DatabaseFactory(db_path)
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(cfg, revision)
        typer.echo(f"Migrations applied to {revision!r}.")
    except Exception as exc:
        typer.echo(f"Migration failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
