"""
Log retention — rotate and compress old app log files.

App logs in logs/app/<date>.jsonl are:
  - Compressed to .jsonl.gz after the day ends.
  - Deleted after settings.logging.retention_days.

Event logs in logs/events/<run_id>.jsonl are kept indefinitely
(deleted only when the session is deleted or via a future maintenance command).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import gzip
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


async def rotate_app_logs(
    log_dir: Path,
    retention_days: int = 30,
) -> None:
    """
    Compress logs older than today and delete logs older than retention_days.

    Should be called once at startup and/or scheduled daily.
    """
    await asyncio.to_thread(_rotate_sync, log_dir, retention_days)


def _rotate_sync(log_dir: Path, retention_days: int) -> None:
    if not log_dir.exists():
        return

    cutoff = datetime.now(tz=UTC) - timedelta(days=retention_days)
    today = datetime.now(tz=UTC).date().isoformat()

    for log_file in sorted(log_dir.glob("*.jsonl")):
        stem = log_file.stem  # "2026-04-07"
        if stem == today:
            continue  # never touch today's log

        try:
            file_date = datetime.fromisoformat(stem).replace(tzinfo=UTC)
        except ValueError:
            continue  # skip non-date filenames

        gz_path = log_file.with_suffix(".jsonl.gz")

        if file_date < cutoff:
            # Past retention — delete both raw and compressed versions
            log_file.unlink(missing_ok=True)
            gz_path.unlink(missing_ok=True)
        elif not gz_path.exists():
            # Older than today but within retention — compress
            _compress(log_file, gz_path)
            log_file.unlink(missing_ok=True)

    # Also delete already-compressed files beyond retention
    for gz_file in sorted(log_dir.glob("*.jsonl.gz")):
        stem = gz_file.stem.removesuffix(".jsonl")
        try:
            file_date = datetime.fromisoformat(stem).replace(tzinfo=UTC)
        except ValueError:
            continue
        if file_date < cutoff:
            gz_file.unlink(missing_ok=True)


def _compress(source: Path, dest: Path) -> None:
    with source.open("rb") as src, gzip.open(str(dest), "wb") as dst:
        shutil.copyfileobj(src, dst)
