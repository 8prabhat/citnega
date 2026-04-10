"""citnega session — create, list, delete, show sessions."""

from __future__ import annotations

import uuid
from typing import Optional

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap
from citnega.packages.protocol.models.sessions import SessionConfig

app = typer.Typer(help="Manage conversation sessions.")


@app.command("new")
@run_async
async def session_new(
    name:      str = typer.Option("default", "--name",      "-n", help="Session name."),
    framework: str = typer.Option("stub",    "--framework", "-f", help="Framework adapter."),
    model:     str = typer.Option("",        "--model",     "-m", help="Default model ID."),
) -> None:
    """Create a new session and print its ID."""
    async with cli_bootstrap() as svc:
        config = SessionConfig(
            session_id=str(uuid.uuid4()),
            name=name,
            framework=framework,
            default_model_id=model or "",
        )
        session = await svc.create_session(config)
        typer.echo(session.config.session_id)


@app.command("list")
@run_async
async def session_list(
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum sessions to show."),
) -> None:
    """List all sessions."""
    async with cli_bootstrap() as svc:
        sessions = await svc.list_sessions(limit=limit)
    if not sessions:
        typer.echo("No sessions found.")
        return
    for s in sessions:
        state = s.state.value if hasattr(s.state, "value") else str(s.state)
        typer.echo(
            f"{s.config.session_id}  {s.config.name:<20}  {state:<10}  "
            f"runs={s.run_count}  {s.last_active_at.strftime('%Y-%m-%d %H:%M')}"
        )


@app.command("show")
@run_async
async def session_show(
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
) -> None:
    """Show details for a single session."""
    async with cli_bootstrap() as svc:
        session = await svc.get_session(session_id)
    if session is None:
        typer.echo(f"Session {session_id!r} not found.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"id:        {session.config.session_id}")
    typer.echo(f"name:      {session.config.name}")
    typer.echo(f"framework: {session.config.framework}")
    typer.echo(f"model:     {session.config.default_model_id}")
    typer.echo(f"state:     {session.state.value}")
    typer.echo(f"runs:      {session.run_count}")
    typer.echo(f"created:   {session.created_at.isoformat()}")
    typer.echo(f"active:    {session.last_active_at.isoformat()}")


@app.command("delete")
@run_async
async def session_delete(
    session_id: str  = typer.Argument(..., help="Session ID to delete."),
    yes:        bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a session and all its associated runs."""
    if not yes:
        confirmed = typer.confirm(f"Delete session {session_id!r}?")
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit()
    async with cli_bootstrap() as svc:
        session = await svc.get_session(session_id)
        if session is None:
            typer.echo(f"Session {session_id!r} not found.", err=True)
            raise typer.Exit(code=1)
        await svc.delete_session(session_id)
    typer.echo(f"Deleted session {session_id}.")
