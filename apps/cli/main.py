"""
Citnega CLI — entry point.

Command tree::

    citnega session   new|list|delete|show
    citnega run       --session <id> --prompt <text>
    citnega approve   <approval_id> [--deny]
    citnega kb        add|search|export
    citnega config    validate|show
    citnega migrate
    citnega jobs      submit|list|logs|cancel|restart
    citnega schedule  add|once|list|show|enable|disable|delete

The CLI depends exclusively on IApplicationService — no direct imports of
runtime, storage, or adapter internals.
"""

from __future__ import annotations

import typer

from citnega.apps.cli.commands import (
    approve,
    config,
    doctor,
    jobs,
    kb,
    migrate,
    remote,
    replay,
    run,
    schedule,
    session,
)

app = typer.Typer(
    name="citnega",
    help="Citnega — platform-agnostic agentic assistant.",
    add_completion=True,
    pretty_exceptions_show_locals=False,
)

app.add_typer(session.app, name="session", help="Manage conversation sessions.")
app.add_typer(run.app, name="run", help="Execute a turn in a session.")
app.add_typer(approve.app, name="approve", help="Respond to a pending approval request.")
app.add_typer(kb.app, name="kb", help="Knowledge base operations (Phase 8).")
app.add_typer(config.app, name="config", help="Validate or display configuration.")
app.add_typer(migrate.app, name="migrate", help="Run database migrations.")
app.add_typer(doctor.app, name="doctor", help="Runtime self-diagnostics (check wiring and config).")
app.add_typer(remote.app, name="remote", help="Reference remote worker service controls.")
app.add_typer(replay.app, name="replay", help="Replay events from a persisted run.")
app.add_typer(jobs.app, name="jobs", help="Submit and manage autonomous agent jobs.")
app.add_typer(schedule.app, name="schedule", help="Manage autonomous agent schedules (cron and one-shot).")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
