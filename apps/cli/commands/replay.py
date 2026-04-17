"""citnega replay — reconstruct the full event timeline of a run from its event log."""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Replay events from a persisted run.")

# Event types considered critical for the timeline summary
_CRITICAL_TYPES = frozenset(
    {
        "RunStateEvent",
        "RunCompleteEvent",
        "RunTerminalReasonEvent",
        "CallableStartEvent",
        "CallableEndEvent",
        "ApprovalRequestEvent",
        "ApprovalResolvedEvent",
        "RouterDecisionEvent",
        "TokenEvent",
        "RateLimitEvent",
        "ContextTruncatedEvent",
        "StartupDiagnosticsEvent",
    }
)


@app.command("replay")
def replay_command(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to replay."),
    json_out: bool = typer.Option(False, "--json", "-j", help="Emit raw JSON events."),
    critical_only: bool = typer.Option(
        False,
        "--critical-only",
        "-c",
        help="Show only state transitions, tool calls, approvals, and completion.",
    ),
    event_log_dir: Path | None = typer.Option(
        None,
        "--event-log-dir",
        help="Override the event log directory (default: auto-detected from app home).",
    ),
) -> None:
    """Replay all persisted events for a run in chronological order.

    Reads ``<event-log-dir>/<run-id>.jsonl`` and prints each event to stdout.
    Use ``--json`` for machine-readable output, or omit for a human-friendly timeline.
    """
    log_path = _resolve_log_path(run_id, event_log_dir)

    if log_path is None or not log_path.exists():
        typer.echo(f"No event log found for run {run_id!r}.", err=True)
        if log_path is not None:
            typer.echo(f"Expected: {log_path}", err=True)
        raise typer.Exit(code=1)

    events = _load_events(log_path)
    if not events:
        typer.echo(f"Event log is empty for run {run_id!r}.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"# Run {run_id}  ({len(events)} events)\n", err=True)

    for raw in events:
        etype = raw.get("event_type", "UnknownEvent")

        if critical_only and etype not in _CRITICAL_TYPES:
            continue

        if json_out:
            typer.echo(json.dumps(raw, default=str))
        else:
            _print_event(raw, etype)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_log_path(run_id: str, override: Path | None) -> Path | None:
    """Return the JSONL log path for *run_id*."""
    if override is not None:
        return override / f"{run_id}.jsonl"
    try:
        from citnega.packages.storage.path_resolver import PathResolver

        resolver = PathResolver()
        return resolver.event_log_path(run_id)
    except Exception:
        return None


def _load_events(path: Path) -> list[dict[str, object]]:
    """Read all JSONL lines from *path*, skipping malformed lines."""
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            typer.echo(f"[warn] line {line_no}: {exc}", err=True)
    return events


def _print_event(raw: dict[str, object], etype: str) -> None:
    """Format one event for human-readable output."""
    ts = raw.get("timestamp", "")
    if isinstance(ts, str) and "T" in ts:
        ts = ts.split("T")[1][:12]  # HH:MM:SS.mmm

    if etype == "TokenEvent":
        # Tokens are noisy — print inline without newline
        token = raw.get("token", "")
        typer.echo(token, nl=False)
        return

    typer.echo("")  # newline after any token run

    if etype == "RunStateEvent":
        typer.echo(
            f"  [{ts}] {raw.get('from_state')} → {raw.get('to_state')}",
            err=False,
        )
    elif etype == "RunCompleteEvent":
        typer.echo(
            f"  [{ts}] COMPLETE: {raw.get('final_state')}",
            err=False,
        )
    elif etype in ("CallableStartEvent", "CallableEndEvent"):
        verb = "START" if etype == "CallableStartEvent" else "END"
        name = raw.get("callable_name") or raw.get("name", "?")
        typer.echo(f"  [{ts}] {verb}: {name}", err=False)
    elif etype in ("ApprovalRequestEvent", "ApprovalResolvedEvent"):
        action = raw.get("action") or raw.get("status", "?")
        typer.echo(f"  [{ts}] APPROVAL {etype.replace('Event', '')}: {action}", err=False)
    elif etype == "RouterDecisionEvent":
        target = raw.get("selected_target", "?")
        typer.echo(f"  [{ts}] ROUTE → {target}", err=False)
    elif etype == "RunTerminalReasonEvent":
        reason = raw.get("reason", "?")
        details = raw.get("details", "")
        suffix = f": {details}" if details else ""
        typer.echo(f"  [{ts}] TERMINAL {reason}{suffix}", err=False)
    elif etype == "StartupDiagnosticsEvent":
        status = raw.get("status", "?")
        failures = raw.get("failures", [])
        suffix = f" failures={failures}" if failures else ""
        typer.echo(f"  [{ts}] STARTUP {status}{suffix}", err=False)
    else:
        typer.echo(f"  [{ts}] {etype}", err=False)
