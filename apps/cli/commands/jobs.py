"""citnega jobs — submit, list, watch, cancel, and restart autonomous agent runs."""

from __future__ import annotations

import asyncio
import json
import uuid

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap

app = typer.Typer(help="Submit and manage autonomous agent jobs.")


# ── helpers ───────────────────────────────────────────────────────────────────

def _ago(dt) -> str:
    from datetime import UTC, datetime
    if dt is None:
        return "—"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=UTC)
    s = int((now - dt).total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def _duration(run) -> str:
    if run.started_at and run.finished_at:
        secs = int((run.finished_at - run.started_at).total_seconds())
        if secs >= 60:
            return f"{secs // 60}m{secs % 60}s"
        return f"{secs}s"
    return "—"


# ── commands ──────────────────────────────────────────────────────────────────

@app.command("submit")
@run_async
async def jobs_submit(
    prompt: str = typer.Option(..., "--prompt", "-p", help="What the agent should do."),
    session: str = typer.Option("", "--session", "-s", help="Session ID (blank = create new autonomous session)."),
    name: str = typer.Option("", "--name", "-n", help="Human label for the job."),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for the run to complete and stream output."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Emit raw JSON events (only with --wait)."),
) -> None:
    """Submit an autonomous agent job.

    Creates a new autonomous session if --session is not given.
    Use --wait to stream output to stdout (like `citnega run`).
    """
    async with cli_bootstrap() as svc:
        session_id = session.strip()

        if not session_id:
            from citnega.packages.protocol.models.sessions import SessionConfig
            frameworks = svc.list_frameworks()
            framework = frameworks[0] if frameworks else "direct"
            models = svc.list_models()
            model_id = models[0].model_id if models else ""
            job_name = name.strip() or prompt[:40].replace("\n", " ")
            config = SessionConfig(
                session_id=str(uuid.uuid4()),
                name=job_name,
                framework=framework,
                default_model_id=model_id,
                session_type="autonomous",
            )
            sess = await svc.create_session(config)
            session_id = sess.config.session_id
            typer.echo(f"Created autonomous session: {session_id}", err=True)

        run_id = await svc.run_turn(session_id, prompt)
        typer.echo(f"run_id:     {run_id}")
        typer.echo(f"session_id: {session_id}")

        if not wait:
            return

        # Stream events to stdout
        from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
        from citnega.packages.protocol.events.streaming import TokenEvent

        exit_code = 0
        try:
            async for event in svc.stream_events(run_id):
                if json_out:
                    typer.echo(json.dumps(event.model_dump(), default=str))
                    continue
                etype = type(event).__name__
                if isinstance(event, TokenEvent):
                    typer.echo(event.token, nl=False)
                elif isinstance(event, RunStateEvent):
                    typer.echo(f"\n[{event.from_state.value} → {event.to_state.value}]", err=True)
                elif isinstance(event, RunCompleteEvent):
                    final = event.final_state.value
                    typer.echo(f"\n[complete: {final}]", err=True)
                    if final not in ("completed", "cancelled"):
                        exit_code = 1
        except (KeyboardInterrupt, asyncio.CancelledError):
            typer.echo("\n[cancelling…]", err=True)
            try:
                await svc.cancel_run(run_id)
            except Exception:
                pass
            exit_code = 130

    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command("list")
@run_async
async def jobs_list(
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum runs to show."),
    session: str = typer.Option("", "--session", "-s", help="Filter by session ID."),
    state: str = typer.Option("", "--state", help="Filter by state: running, completed, failed, all."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Output as JSON lines."),
) -> None:
    """List recent autonomous agent runs across all sessions."""
    async with cli_bootstrap() as svc:
        if session.strip():
            runs = await svc.list_runs(session.strip(), limit=limit)
        else:
            runs = await svc.list_all_runs(limit=limit)

    if state and state != "all":
        runs = [r for r in runs if r.state.value == state]

    if not runs:
        typer.echo("No runs found.")
        return

    if json_out:
        for r in runs:
            typer.echo(json.dumps(r.model_dump(), default=str))
        return

    header = f"{'RUN ID':<38}  {'SESSION':<12}  {'STATE':<18}  {'STARTED':<12}  {'DUR':<8}  PROMPT"
    typer.echo(header)
    typer.echo("─" * len(header))
    for r in runs:
        state_val = r.state.value
        prompt_short = (r.user_input or "")[:40] or f"<run/{r.run_id[:8]}>"
        typer.echo(
            f"{r.run_id:<38}  {r.session_id[:12]:<12}  {state_val:<18}  "
            f"{_ago(r.started_at):<12}  {_duration(r):<8}  {prompt_short}"
        )


@app.command("logs")
@run_async
async def jobs_logs(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to stream events for."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Emit raw JSON events."),
) -> None:
    """Stream live events for a running or in-progress job.

    Attach to any run_id — whether it was started by the scheduler,
    the TUI, or `citnega jobs submit`.
    """
    from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
    from citnega.packages.protocol.events.streaming import TokenEvent
    from citnega.packages.protocol.events import CallableStartEvent, CallableEndEvent

    async with cli_bootstrap() as svc:
        run = await svc.get_run(run_id)
        if run is None:
            typer.echo(f"Run {run_id!r} not found.", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Attaching to run {run_id[:8]}…  (state: {run.state.value})", err=True)
        exit_code = 0
        try:
            async for event in svc.stream_events(run_id):
                if json_out:
                    typer.echo(json.dumps(event.model_dump(), default=str))
                    continue
                if isinstance(event, TokenEvent):
                    typer.echo(event.token, nl=False)
                elif isinstance(event, RunStateEvent):
                    typer.echo(f"\n[{event.from_state.value} → {event.to_state.value}]", err=True)
                elif isinstance(event, CallableStartEvent):
                    typer.echo(f"\n  ⚙ {event.callable_name}({event.input_summary[:60]})", err=True)
                elif isinstance(event, CallableEndEvent):
                    ok = "✓" if event.error_code is None else "✗"
                    typer.echo(f"    {ok} {(event.output_summary or '')[:80]}", err=True)
                elif isinstance(event, RunCompleteEvent):
                    final = event.final_state.value
                    typer.echo(f"\n[complete: {final}]", err=True)
                    if final not in ("completed", "cancelled"):
                        exit_code = 1
        except (KeyboardInterrupt, asyncio.CancelledError):
            typer.echo("\n[detached]", err=True)

    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command("cancel")
@run_async
async def jobs_cancel(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to cancel."),
) -> None:
    """Cancel an active or queued autonomous run."""
    async with cli_bootstrap() as svc:
        run = await svc.get_run(run_id)
        if run is None:
            typer.echo(f"Run {run_id!r} not found.", err=True)
            raise typer.Exit(code=1)
        try:
            await svc.cancel_run(run_id)
            typer.echo(f"Run {run_id[:8]}… cancelled.")
        except Exception as exc:
            typer.echo(f"Cancel failed: {exc}", err=True)
            raise typer.Exit(code=1)


@app.command("restart")
@run_async
async def jobs_restart(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to restart."),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for the new run to complete."),
) -> None:
    """Restart a job using the same session and prompt as the original run."""
    async with cli_bootstrap() as svc:
        run = await svc.get_run(run_id)
        if run is None:
            typer.echo(f"Run {run_id!r} not found.", err=True)
            raise typer.Exit(code=1)

        if not run.user_input:
            typer.echo("No stored prompt — cannot restart (run was created before v0.6.1).", err=True)
            raise typer.Exit(code=1)

        new_run_id = await svc.run_turn(run.session_id, run.user_input)
        typer.echo(f"Restarted.  new run_id: {new_run_id}")

        if not wait:
            return

        from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
        from citnega.packages.protocol.events.streaming import TokenEvent

        async for event in svc.stream_events(new_run_id):
            if isinstance(event, TokenEvent):
                typer.echo(event.token, nl=False)
            elif isinstance(event, RunStateEvent):
                typer.echo(f"\n[{event.from_state.value} → {event.to_state.value}]", err=True)
            elif isinstance(event, RunCompleteEvent):
                typer.echo(f"\n[complete: {event.final_state.value}]", err=True)
                break
