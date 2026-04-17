"""citnega session — create, list, delete, show sessions."""

from __future__ import annotations

import uuid

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap
from citnega.packages.protocol.models.sessions import SessionConfig

app = typer.Typer(help="Manage conversation sessions.")


@app.command("new")
@run_async
async def session_new(
    name: str = typer.Option("default", "--name", "-n", help="Session name."),
    framework: str = typer.Option(
        "",
        "--framework",
        "-f",
        help="Framework adapter (default: active runtime adapter).",
    ),
    model: str = typer.Option(
        "",
        "--model",
        "-m",
        help="Default model ID (default: highest-priority available model).",
    ),
) -> None:
    """Create a new session and print its ID."""
    async with cli_bootstrap() as svc:
        framework_id = framework
        if not framework_id:
            frameworks = svc.list_frameworks()
            if isinstance(frameworks, list) and frameworks and isinstance(frameworks[0], str):
                framework_id = frameworks[0]
            else:
                framework_id = "direct"

        model_id = model
        if not model_id:
            models = svc.list_models()
            if isinstance(models, list) and models and isinstance(models[0].model_id, str):
                model_id = models[0].model_id
            else:
                model_id = ""

        config = SessionConfig(
            session_id=str(uuid.uuid4()),
            name=name,
            framework=framework_id,
            default_model_id=model_id,
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
        state = s.state.value
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


@app.command("rename")
@run_async
async def session_rename(
    session_id: str = typer.Argument(..., help="Session ID to rename."),
    name: str = typer.Argument(..., help="New name for the session."),
) -> None:
    """Rename a session."""
    async with cli_bootstrap() as svc:
        session = await svc.get_session(session_id)
        if session is None:
            typer.echo(f"Session {session_id!r} not found.", err=True)
            raise typer.Exit(code=1)
        await svc.rename_session(session_id, name)
    typer.echo(f"Renamed session {session_id} to {name!r}.")


@app.command("delete")
@run_async
async def session_delete(
    session_id: str = typer.Argument(..., help="Session ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
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
