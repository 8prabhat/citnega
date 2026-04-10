"""
packages/bootstrap/shutdown.py — Graceful shutdown handler.

Responsibilities:
  - Install SIGTERM / SIGINT signal handlers.
  - On signal: cancel active runs, drain the event emitter queues,
    close the database connection, and emit a shutdown event.
  - Expose ``ShutdownCoordinator`` so the composition root can wire it up
    without importing signal machinery directly.

Usage (from bootstrap.py)::

    coordinator = ShutdownCoordinator(runtime, emitter, db)
    coordinator.install()

    # Later, on clean exit:
    await coordinator.shutdown()
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger

if TYPE_CHECKING:
    from citnega.packages.runtime.core_runtime import CoreRuntime
    from citnega.packages.runtime.events.emitter import EventEmitter
    from citnega.packages.storage.database import DatabaseFactory


# How long (seconds) to wait for the event-queue drain before giving up.
_DRAIN_TIMEOUT = 5.0


class ShutdownCoordinator:
    """
    Wires SIGTERM / SIGINT to a graceful async shutdown sequence.

    Steps on signal receipt:
      1. Set the shutdown flag (idempotent — second signal exits immediately).
      2. Cancel all active runs via ``CoreRuntime.shutdown()``.
      3. Drain open EventEmitter queues (up to ``_DRAIN_TIMEOUT`` seconds).
      4. Disconnect the database.
      5. Log shutdown complete and call ``sys.exit(0)``.
    """

    def __init__(
        self,
        runtime: "CoreRuntime",
        emitter: "EventEmitter",
        db: "DatabaseFactory",
    ) -> None:
        self._runtime = runtime
        self._emitter = emitter
        self._db = db
        self._shutdown_flag = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def install(self) -> None:
        """
        Install SIGTERM and SIGINT handlers on the running event loop.

        Must be called from within a running asyncio event loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            runtime_logger.warning("shutdown_install_no_loop")
            return

        self._loop = loop

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except (NotImplementedError, OSError):
                # Windows: add_signal_handler not supported for SIGTERM;
                # fall back to signal.signal for SIGINT only.
                if sig == signal.SIGINT:
                    signal.signal(signal.SIGINT, self._handle_signal_sync)

        runtime_logger.info("shutdown_handlers_installed")

    async def shutdown(self) -> None:
        """
        Execute the full graceful shutdown sequence.

        Safe to call multiple times (idempotent via _shutdown_flag).
        """
        if self._shutdown_flag.is_set():
            return
        self._shutdown_flag.set()

        runtime_logger.info("shutdown_start")

        # 1. Cancel active runs
        try:
            await self._runtime.shutdown()
        except Exception as exc:
            runtime_logger.warning("shutdown_runtime_error", error=str(exc))

        # 2. Drain event queues
        await self._drain_queues()

        # 3. Disconnect database
        try:
            await self._db.disconnect()
        except Exception as exc:
            runtime_logger.warning("shutdown_db_disconnect_error", error=str(exc))

        runtime_logger.info("shutdown_complete")

    @property
    def shutdown_requested(self) -> bool:
        """True once a shutdown signal has been received."""
        return self._shutdown_flag.is_set()

    async def wait_for_shutdown(self) -> None:
        """Coroutine that returns only when shutdown is requested."""
        await self._shutdown_flag.wait()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _handle_signal(self) -> None:
        """Synchronous signal callback registered via loop.add_signal_handler()."""
        if self._shutdown_flag.is_set():
            # Second signal — hard exit
            runtime_logger.warning("shutdown_force_exit")
            sys.exit(1)

        runtime_logger.info("shutdown_signal_received")

        if self._loop is not None:
            self._loop.create_task(self.shutdown())

    def _handle_signal_sync(self, signum: int, frame: object) -> None:
        """Fallback for Windows SIGINT."""
        self._handle_signal()

    async def _drain_queues(self) -> None:
        """
        Wait for all open event queues to empty, up to _DRAIN_TIMEOUT seconds.

        EventEmitter stores queues in ``_queues`` (dict keyed by run_id).
        We iterate a snapshot so new queues added during drain are ignored.
        """
        queues = {}
        try:
            import threading  # noqa: PLC0415
            with self._emitter._lock:
                queues = dict(self._emitter._queues)
        except Exception:
            return  # can't access internal state — skip drain

        if not queues:
            return

        runtime_logger.info("shutdown_draining_queues", queue_count=len(queues))

        async def _drain_one(run_id: str, queue: asyncio.Queue) -> None:  # type: ignore[type-arg]
            deadline = asyncio.get_event_loop().time() + _DRAIN_TIMEOUT
            while not queue.empty():
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    runtime_logger.warning(
                        "shutdown_drain_timeout", run_id=run_id, remaining=queue.qsize()
                    )
                    break
                await asyncio.sleep(0.05)

        drain_tasks = [
            asyncio.create_task(_drain_one(rid, q)) for rid, q in queues.items()
        ]
        if drain_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*drain_tasks, return_exceptions=True),
                    timeout=_DRAIN_TIMEOUT + 1.0,
                )
            except asyncio.TimeoutError:
                runtime_logger.warning("shutdown_drain_global_timeout")

        runtime_logger.info("shutdown_queues_drained")
