"""Startup and runtime diagnostics events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class StartupDiagnosticsEvent(BaseEvent):
    """
    Emitted once during application startup after all health checks run.

    Fields
    ------
    checks
        Ordered list of check names that were evaluated
        (e.g. ``["db_connection", "adapter_health", "model_gateway"]``).
    status
        Overall result: ``"passed"`` | ``"degraded"`` | ``"failed"``.
        ``"degraded"`` means non-critical checks failed but the runtime
        started anyway (e.g. model gateway unreachable but local mode active).
    failures
        Names of checks that did not pass.  Empty list on full success.
    details
        Optional per-check detail map for richer diagnostics output.
    """

    event_type: str = "StartupDiagnosticsEvent"
    checks: list[str]
    status: str  # "passed" | "degraded" | "failed"
    failures: list[str]
    details: dict[str, str] = {}  # check_name → detail message
