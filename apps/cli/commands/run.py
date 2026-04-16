"""citnega run — execute a turn in a session and stream events to stdout."""

from __future__ import annotations

import asyncio
import json

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap
from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
from citnega.packages.protocol.events.streaming import TokenEvent

app = typer.Typer(help="Run a turn in a session.")

# Events worth printing to the terminal
_VERBOSE_TYPES = frozenset(
    {
        "RunStateEvent",
        "CallableStartEvent",
        "CallableEndEvent",
        "ApprovalRequestEvent",
        "RateLimitEvent",
        "TokenEvent",
        "RunCompleteEvent",
    }
)


@app.command("run")
@run_async
async def run_command(
    session_id: str = typer.Option(..., "--session", "-s", help="Session ID."),
    prompt: str = typer.Option(..., "--prompt", "-p", help="User input text."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Emit raw JSON events."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress event output."),
) -> None:
    """Start a turn and stream its events to stdout until completion.

    Press Ctrl+C to cancel the active run gracefully.
    """
    async with cli_bootstrap() as svc:
        # Verify session exists
        session = await svc.get_session(session_id)
        if session is None:
            typer.echo(f"Session {session_id!r} not found.", err=True)
            raise typer.Exit(code=1)

        run_id = await svc.run_turn(session_id, prompt)

        if not quiet:
            typer.echo(f"run_id: {run_id}", err=True)

        exit_code = 0
        try:
            async for event in svc.stream_events(run_id):
                if quiet:
                    continue

                if json_out:
                    typer.echo(json.dumps(event.model_dump(), default=str))
                    continue

                etype = type(event).__name__
                if etype not in _VERBOSE_TYPES:
                    continue

                if isinstance(event, TokenEvent):
                    typer.echo(event.token, nl=False)

                elif isinstance(event, RunStateEvent):
                    typer.echo(
                        f"\n[{event.from_state.value} → {event.to_state.value}]",
                        err=True,
                    )

                elif isinstance(event, RunCompleteEvent):
                    final = event.final_state.value
                    typer.echo(f"\n[complete: {final}]", err=True)
                    if final not in ("completed", "cancelled"):
                        exit_code = 1

                else:
                    typer.echo(f"[{etype}]", err=True)

        except (KeyboardInterrupt, asyncio.CancelledError):
            typer.echo("\n[cancelling…]", err=True)
            try:
                await svc.cancel_run(run_id)
                typer.echo(f"[run {run_id[:8]} cancelled]", err=True)
            except Exception as exc:
                typer.echo(f"[cancel failed: {exc}]", err=True)
            exit_code = 130  # standard Ctrl+C exit code

    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command("cancel")
@run_async
async def cancel_command(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to cancel."),
) -> None:
    """Cancel an active or queued run by its ID."""
    async with cli_bootstrap() as svc:
        try:
            await svc.cancel_run(run_id)
            typer.echo(f"Run {run_id} cancelled.")
        except Exception as exc:
            typer.echo(f"Cancel failed: {exc}", err=True)
            raise typer.Exit(code=1)


# Allow `citnega run` as a shorthand (no sub-subcommand needed)
# Typer's default is the first command; expose the app at module level.
