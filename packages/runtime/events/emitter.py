"""
EventEmitter — bounded asyncio.Queue-based event fan-out.

One queue per run_id (maxsize=256). Applying backpressure to the framework
runner when the consumer (TUI Worker / CLI) falls behind.

Usage:
  emitter.emit(event)          → put_nowait into the run's queue
  emitter.get_queue(run_id)    → for consumers to drain
  emitter.close_queue(run_id)  → send RunCompleteEvent sentinel + remove queue
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.events import IEventEmitter
from citnega.packages.security.scrubber import scrub_dict

if TYPE_CHECKING:
    from pathlib import Path

    from citnega.packages.protocol.events import CanonicalEvent

_QUEUE_MAXSIZE = 256


class EventEmitter(IEventEmitter):
    """
    Thread-safe, per-run asyncio.Queue event emitter.

    ``emit()`` is synchronous and non-blocking. If the queue is full,
    the oldest event is dropped and a warning is logged (backpressure
    signal — the consumer is too slow).

    Events are also written to JSONL event logs if an event_log_dir is set.
    """

    def __init__(self, event_log_dir: Path | None = None) -> None:
        self._queues: dict[str, asyncio.Queue[CanonicalEvent]] = {}
        self._lock = threading.Lock()
        self._event_log_dir = event_log_dir

    # ── IEventEmitter ──────────────────────────────────────────────────────────

    def emit(self, event: CanonicalEvent) -> None:
        """Emit an event to the run's queue (non-blocking)."""
        run_id = event.run_id
        queue = self._get_or_create_queue(run_id)

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest and retry — consumers are falling behind
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                runtime_logger.warning(
                    "event_dropped",
                    run_id=run_id,
                    event_type=event.event_type,
                )
                return

        # Write to JSONL event log asynchronously (fire-and-forget)
        if self._event_log_dir is not None:
            self._write_event_jsonl(event)

    def get_queue(self, run_id: str) -> asyncio.Queue[CanonicalEvent]:
        return self._get_or_create_queue(run_id)

    def close_queue(self, run_id: str) -> None:
        """Mark the queue as closed. Consumers receive no more events."""
        with self._lock:
            self._queues.pop(run_id, None)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _get_or_create_queue(self, run_id: str) -> asyncio.Queue[CanonicalEvent]:
        with self._lock:
            if run_id not in self._queues:
                self._queues[run_id] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
            return self._queues[run_id]

    def _write_event_jsonl(self, event: CanonicalEvent) -> None:
        """Write event to JSONL log file (best-effort, no exception propagation)."""
        try:
            log_path = self._event_log_dir / f"{event.run_id}.jsonl"  # type: ignore[operator]
            raw = event.model_dump()
            scrubbed = scrub_dict(raw)
            line = json.dumps(scrubbed, default=str) + "\n"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception as exc:
            runtime_logger.warning("event_log_write_failed", error=str(exc))
