#!/usr/bin/env python
"""
scripts/replay.py — Event log replay harness.

Reads a run's JSONL event log and reconstructs the run state by replaying
events in order, printing a human-readable timeline and a final state diff
compared to the persisted database record.

Usage::

    python scripts/replay.py <run_id>
    python scripts/replay.py <run_id> --db /path/to/citnega.db
    python scripts/replay.py <run_id> --event-log /path/to/<run_id>.jsonl
    python scripts/replay.py <run_id> --json       # machine-readable output

Exit codes:
  0 — replay succeeded, state matches DB record
  1 — event log not found
  2 — replay succeeded, state DIVERGES from DB record (post-mortem flag)
  3 — DB record not found (orphaned event log)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# State reconstructed from event stream
# ---------------------------------------------------------------------------

@dataclass
class ReplayedState:
    run_id: str
    session_id: str | None = None
    state: str = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    turn_count: int = 0
    total_tokens: int = 0
    error_message: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    callable_invocations: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, event: dict[str, Any]) -> None:
        """Apply a single event dict to update reconstructed state."""
        self.events.append(event)
        etype = event.get("event_type", "")

        if self.session_id is None:
            self.session_id = event.get("session_id")

        if etype == "run_state":
            new_state = event.get("new_state", "")
            if new_state:
                self.state = new_state
            if new_state == "executing" and self.started_at is None:
                ts = event.get("ts")
                if ts:
                    self.started_at = _parse_ts(ts)

        elif etype == "run_complete":
            self.state = event.get("final_state", "completed")
            ts = event.get("ts")
            if ts:
                self.finished_at = _parse_ts(ts)
            self.total_tokens = event.get("total_tokens", self.total_tokens)
            self.turn_count = event.get("turn_count", self.turn_count)
            err = event.get("error_message")
            if err:
                self.error_message = err

        elif etype == "callable_start":
            self.callable_invocations.append({
                "event_id": event.get("event_id"),
                "callable_name": event.get("callable_name"),
                "started_at": event.get("ts"),
                "finished_at": None,
                "success": None,
            })

        elif etype == "callable_end":
            ev_id = event.get("event_id")
            for inv in self.callable_invocations:
                if inv["event_id"] == ev_id:
                    inv["finished_at"] = event.get("ts")
                    inv["success"] = event.get("error_code") is None
                    break

        elif etype == "token":
            # Count tokens from streaming events if total_tokens not yet set
            pass  # token events don't carry a running total


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Event log reader
# ---------------------------------------------------------------------------

def load_event_log(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL event log and return a list of event dicts."""
    events = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(
                    f"[replay] WARNING: line {lineno} not valid JSON ({exc}) — skipped",
                    file=sys.stderr,
                )
    return events


# ---------------------------------------------------------------------------
# DB record loader
# ---------------------------------------------------------------------------

async def load_db_record(run_id: str, db_path: Path) -> dict[str, Any] | None:
    """Query the runs table for the given run_id."""
    try:
        import aiosqlite
    except ImportError:
        return None

    if not db_path.exists():
        return None

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)


# ---------------------------------------------------------------------------
# Diff helper
# ---------------------------------------------------------------------------

def diff_states(replayed: ReplayedState, db: dict[str, Any]) -> list[str]:
    """Return a list of divergence messages (empty = states match)."""
    divergences = []

    def _check(field: str, replayed_val: Any, db_val: Any) -> None:
        if str(replayed_val or "") != str(db_val or ""):
            divergences.append(
                f"  {field}: replayed={replayed_val!r}  db={db_val!r}"
            )

    _check("state", replayed.state, db.get("state"))
    _check("session_id", replayed.session_id, db.get("session_id"))
    _check("error_message", replayed.error_message, db.get("error_message"))

    return divergences


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def print_timeline(replayed: ReplayedState) -> None:
    print(f"\nRun ID   : {replayed.run_id}")
    print(f"Session  : {replayed.session_id or '(unknown)'}")
    print(f"State    : {replayed.state}")
    print(f"Started  : {replayed.started_at or '(unknown)'}")
    print(f"Finished : {replayed.finished_at or '(unknown)'}")
    print(f"Tokens   : {replayed.total_tokens}")
    print(f"Events   : {len(replayed.events)}")
    print(f"Callables: {len(replayed.callable_invocations)}")

    if replayed.error_message:
        print(f"Error    : {replayed.error_message}")

    if replayed.callable_invocations:
        print("\nCallable invocations:")
        for inv in replayed.callable_invocations:
            status = "ok" if inv.get("success") else ("FAIL" if inv.get("success") is False else "?")
            print(f"  [{status}] {inv.get('callable_name', '?')}  started={inv.get('started_at', '?')}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _resolve_event_log(run_id: str, event_log_override: Path | None) -> Path | None:
    if event_log_override is not None:
        return event_log_override

    # Try default PathResolver location
    try:
        from citnega.packages.storage.path_resolver import PathResolver
        resolver = PathResolver()
        candidate = resolver.event_log_path(run_id)
        if candidate.exists():
            return candidate
    except Exception:
        pass

    # Fallback: look in current directory
    local = Path(f"{run_id}.jsonl")
    if local.exists():
        return local

    return None


async def _main(args: argparse.Namespace) -> int:
    run_id: str = args.run_id
    as_json: bool = args.json

    # 1. Locate event log
    event_log_path = _resolve_event_log(
        run_id,
        Path(args.event_log) if args.event_log else None,
    )
    if event_log_path is None or not event_log_path.exists():
        msg = f"Event log not found for run_id={run_id!r}"
        if as_json:
            print(json.dumps({"error": msg}))
        else:
            print(f"[replay] ERROR: {msg}", file=sys.stderr)
        return 1

    # 2. Load events
    raw_events = load_event_log(event_log_path)

    # 3. Replay
    replayed = ReplayedState(run_id=run_id)
    for ev in raw_events:
        replayed.apply(ev)

    # 4. Load DB record
    db_path = Path(args.db) if args.db else None
    if db_path is None:
        try:
            from citnega.packages.storage.path_resolver import PathResolver
            db_path = PathResolver().db_path
        except Exception:
            db_path = None

    db_record: dict[str, Any] | None = None
    if db_path is not None:
        db_record = await load_db_record(run_id, db_path)

    # 5. Diff
    divergences: list[str] = []
    if db_record is not None:
        divergences = diff_states(replayed, db_record)
    elif db_path is not None and db_path.exists():
        divergences = ["  DB record not found (orphaned event log)"]

    # 6. Output
    if as_json:
        output = {
            "run_id": run_id,
            "replayed_state": replayed.state,
            "session_id": replayed.session_id,
            "started_at": replayed.started_at.isoformat() if replayed.started_at else None,
            "finished_at": replayed.finished_at.isoformat() if replayed.finished_at else None,
            "total_tokens": replayed.total_tokens,
            "event_count": len(replayed.events),
            "callable_count": len(replayed.callable_invocations),
            "error_message": replayed.error_message,
            "divergences": divergences,
            "db_record": db_record,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_timeline(replayed)

        if db_record is None and db_path is not None and db_path.exists():
            print("[replay] WARNING: no DB record found — orphaned event log")
            return 3

        if divergences:
            print("[replay] STATE DIVERGENCE DETECTED:")
            for d in divergences:
                print(d)
            print()
            return 2

        if db_record is not None:
            print("[replay] OK — replayed state matches DB record.")

    return 0 if not divergences else 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a Citnega run from its JSONL event log."
    )
    parser.add_argument("run_id", help="The run ID to replay")
    parser.add_argument("--db", help="Path to citnega.db (default: platform default)")
    parser.add_argument("--event-log", help="Path to JSONL event log (default: auto-detect)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text")
    args = parser.parse_args()

    exit_code = asyncio.run(_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
