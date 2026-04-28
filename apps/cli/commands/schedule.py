"""citnega schedule — manage autonomous agent cron and one-shot schedules."""

from __future__ import annotations

import json
import uuid

import typer

from citnega.apps.cli._async import run_async
from citnega.apps.cli.bootstrap import cli_bootstrap

app = typer.Typer(help="Manage autonomous agent schedules (cron and one-shot).")


# ── helpers ───────────────────────────────────────────────────────────────────

def _ago(dt) -> str:
    from datetime import UTC, datetime
    if dt is None:
        return "never"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    s = int((now - dt).total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def _until(dt) -> str:
    from datetime import UTC, datetime
    if dt is None:
        return "—"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    s = int((dt - now).total_seconds())
    if s < 0:
        return "overdue"
    if s < 60:
        return f"in {s}s"
    if s < 3600:
        return f"in {s // 60}m"
    if s < 86400:
        return f"in {s // 3600}h"
    return f"in {s // 86400}d"


def _require_scheduler(svc) -> object:
    sched = getattr(svc, "scheduler", None)
    if sched is None:
        typer.echo(
            "SchedulerService is not available — check bootstrap logs.",
            err=True,
        )
        raise typer.Exit(code=1)
    return sched


def _ensure_autonomous_session(svc, session_id: str, name: str) -> str:
    """Create a new autonomous session if session_id is blank."""
    import asyncio
    if session_id:
        return session_id
    raise RuntimeError("call _async_ensure_autonomous_session from async context")


async def _async_ensure_session(svc, session_id: str, name: str) -> str:
    if session_id.strip():
        return session_id.strip()
    from citnega.packages.protocol.models.sessions import SessionConfig
    frameworks = svc.list_frameworks()
    framework = frameworks[0] if frameworks else "direct"
    models = svc.list_models()
    model_id = models[0].model_id if models else ""
    config = SessionConfig(
        session_id=str(uuid.uuid4()),
        name=name or "autonomous",
        framework=framework,
        default_model_id=model_id,
        session_type="autonomous",
    )
    sess = await svc.create_session(config)
    typer.echo(f"Created autonomous session: {sess.config.session_id}", err=True)
    return sess.config.session_id


# ── commands ──────────────────────────────────────────────────────────────────

@app.command("add")
@run_async
async def schedule_add(
    name: str = typer.Option(..., "--name", "-n", help="Human label for this schedule."),
    cron: str = typer.Option(..., "--cron", "-c", help='Cron expression, e.g. "0 9 * * 1-5".'),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt sent to the agent on each fire."),
    session: str = typer.Option("", "--session", "-s", help="Session ID (blank = create new autonomous session)."),
    disabled: bool = typer.Option(False, "--disabled", help="Create the schedule in disabled state."),
) -> None:
    """Add a recurring cron schedule.

    Examples:

      \b
      # Every weekday at 9 am
      citnega schedule add --name standup --cron "0 9 * * 1-5" \\
          --prompt "Generate today's standup" --session <id>

      \b
      # Every 15 minutes
      citnega schedule add --name heartbeat --cron "*/15 * * * *" \\
          --prompt "Check system health" --session <id>
    """
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        session_id = await _async_ensure_session(svc, session, name)

        from citnega.packages.protocol.models.scheduler import CreateScheduleRequest
        sched = await scheduler.create_schedule(
            CreateScheduleRequest(
                name=name,
                schedule=cron,
                session_id=session_id,
                prompt=prompt,
                enabled=not disabled,
            )
        )
    typer.echo(f"schedule_id: {sched.schedule_id}")
    typer.echo(f"name:        {sched.name}")
    typer.echo(f"cron:        {sched.schedule}")
    typer.echo(f"session:     {sched.session_id}")
    typer.echo(f"enabled:     {sched.enabled}")


@app.command("once")
@run_async
async def schedule_once(
    name: str = typer.Option(..., "--name", "-n", help="Human label for this job."),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt sent to the agent."),
    at: str = typer.Option(..., "--at", help='ISO datetime to fire, e.g. "2026-04-22T15:00:00".'),
    session: str = typer.Option("", "--session", "-s", help="Session ID (blank = create new autonomous session)."),
) -> None:
    """Schedule a one-shot job to run at a specific date and time.

    Example:

      \b
      citnega schedule once --name post-deploy \\
          --prompt "Run smoke tests and report" \\
          --at "2026-04-22T16:00:00" \\
          --session <id>
    """
    from datetime import UTC, datetime

    try:
        fire_at = datetime.fromisoformat(at)
        if fire_at.tzinfo is None:
            fire_at = fire_at.replace(tzinfo=UTC)
    except ValueError:
        typer.echo(f"Invalid --at value {at!r} — use ISO format: 2026-04-22T15:00:00", err=True)
        raise typer.Exit(code=1)

    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        session_id = await _async_ensure_session(svc, session, name)
        sched = await scheduler.schedule_once(
            name=name,
            session_id=session_id,
            prompt=prompt,
            fire_at=fire_at,
        )
    typer.echo(f"schedule_id: {sched.schedule_id}")
    typer.echo(f"fires at:    {sched.next_fire_at.isoformat()}")
    typer.echo(f"({_until(sched.next_fire_at)})")


@app.command("list")
@run_async
async def schedule_list(
    all_schedules: bool = typer.Option(False, "--all", "-a", help="Include disabled schedules."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Output as JSON lines."),
) -> None:
    """List autonomous agent schedules."""
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        schedules = await scheduler.list_schedules(enabled_only=not all_schedules)

    if not schedules:
        typer.echo("No schedules found.")
        return

    if json_out:
        for s in schedules:
            typer.echo(json.dumps(s.model_dump(), default=str))
        return

    header = f"{'SCHEDULE ID':<38}  {'NAME':<20}  {'SCHEDULE':<18}  {'STATUS':<10}  {'SESSION':<12}  LAST FIRED"
    typer.echo(header)
    typer.echo("─" * len(header))
    for s in schedules:
        status = "enabled" if s.enabled else "disabled"
        when = _until(s.next_fire_at) if s.schedule == "once" else _ago(s.last_fired_at)
        typer.echo(
            f"{s.schedule_id:<38}  {s.name:<20}  {s.schedule:<18}  "
            f"{status:<10}  {s.session_id[:12]:<12}  {when}"
        )


@app.command("show")
@run_async
async def schedule_show(
    schedule_id: str = typer.Argument(..., help="Schedule ID to inspect."),
) -> None:
    """Show full details for a single schedule."""
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        sched = await scheduler.get_schedule(schedule_id)
    if sched is None:
        typer.echo(f"Schedule {schedule_id!r} not found.", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"id:           {sched.schedule_id}")
    typer.echo(f"name:         {sched.name}")
    typer.echo(f"schedule:     {sched.schedule}")
    typer.echo(f"session:      {sched.session_id}")
    typer.echo(f"prompt:       {sched.prompt}")
    typer.echo(f"enabled:      {sched.enabled}")
    typer.echo(f"last_fired:   {sched.last_fired_at.isoformat() if sched.last_fired_at else 'never'}")
    typer.echo(f"next_fire:    {sched.next_fire_at.isoformat() if sched.next_fire_at else '—'}")
    typer.echo(f"created:      {sched.created_at.isoformat()}")


@app.command("enable")
@run_async
async def schedule_enable(
    schedule_id: str = typer.Argument(..., help="Schedule ID to enable."),
) -> None:
    """Enable a disabled schedule."""
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        await scheduler.enable_schedule(schedule_id)
    typer.echo(f"Schedule {schedule_id[:8]}… enabled.")


@app.command("disable")
@run_async
async def schedule_disable(
    schedule_id: str = typer.Argument(..., help="Schedule ID to disable."),
) -> None:
    """Disable a schedule without deleting it."""
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        await scheduler.disable_schedule(schedule_id)
    typer.echo(f"Schedule {schedule_id[:8]}… disabled.")


@app.command("delete")
@run_async
async def schedule_delete(
    schedule_id: str = typer.Argument(..., help="Schedule ID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Permanently delete a schedule."""
    if not yes:
        confirmed = typer.confirm(f"Delete schedule {schedule_id!r}?")
        if not confirmed:
            typer.echo("Aborted.")
            raise typer.Exit()
    async with cli_bootstrap() as svc:
        scheduler = _require_scheduler(svc)
        await scheduler.delete_schedule(schedule_id)
    typer.echo(f"Schedule {schedule_id[:8]}… deleted.")
