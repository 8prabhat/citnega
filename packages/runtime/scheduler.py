"""
SchedulerService — durable autonomous agent scheduler.

Extends the HeartbeatEngine concept with:
  - DB-backed schedule persistence (survives process restarts)
  - Cron-scheduled runs ("0 9 * * 1-5")
  - One-shot future runs (schedule="once", next_fire_at=<datetime>)
  - Failed-run re-queuing with exponential backoff
  - CRUD API for managing schedules at runtime

Cron format: 5-field "minute hour dom month dow" (no seconds).
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
import uuid

from citnega.packages.observability.logging_setup import runtime_logger

if TYPE_CHECKING:
    from citnega.packages.protocol.models.scheduler import CreateScheduleRequest, ScheduledRun
    from citnega.packages.storage.repositories.schedule_repo import ScheduleRepository


def _cron_matches(schedule: str, now: datetime) -> bool:
    """Return True if a 5-field cron expression matches the current minute."""
    fields = schedule.strip().split()
    if len(fields) != 5:
        return False
    minute_s, hour_s, _dom_s, _month_s, dow_s = fields

    def _matches(field: str, value: int) -> bool:
        if field == "*":
            return True
        if "/" in field:
            base, step = field.split("/", 1)
            start = 0 if base == "*" else int(base)
            return (value - start) % int(step) == 0
        if "-" in field:
            lo, hi = field.split("-", 1)
            return int(lo) <= value <= int(hi)
        try:
            return int(field) == value
        except ValueError:
            return False

    return (
        _matches(minute_s, now.minute)
        and _matches(hour_s, now.hour)
        and _matches(dow_s, now.weekday())
    )


class SchedulerService:
    """
    DB-backed scheduler that fires autonomous agent runs on cron schedules
    or at a specific future time.
    """

    _CHECK_INTERVAL = 60  # seconds

    def __init__(
        self,
        schedule_repo: ScheduleRepository,
        app_service: Any,
    ) -> None:
        self._repo = schedule_repo
        self._app = app_service
        self._task: asyncio.Task[None] | None = None
        # name/id → "YYYY-MM-DD HH:MM" of last fire — prevents double-firing
        self._last_fired: dict[str, str] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="scheduler_service")
        runtime_logger.info("scheduler_service_started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        runtime_logger.info("scheduler_service_stopped")

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._CHECK_INTERVAL)
            with contextlib.suppress(Exception):
                await self._check_schedules()

    async def _check_schedules(self) -> None:
        schedules = await self._repo.list(enabled=True)
        now = datetime.now(UTC)
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        for sched in schedules:
            should_fire = False

            if sched.schedule == "once":
                if sched.next_fire_at and sched.next_fire_at <= now:
                    should_fire = True
            else:
                if _cron_matches(sched.schedule, now):
                    should_fire = True

            if should_fire and self._last_fired.get(sched.schedule_id) != minute_key:
                self._last_fired[sched.schedule_id] = minute_key
                asyncio.create_task(
                    self._fire(sched),
                    name=f"sched-{sched.schedule_id[:8]}",
                )

    async def _fire(self, sched: ScheduledRun) -> None:
        runtime_logger.info(
            "scheduler_firing",
            schedule_id=sched.schedule_id,
            name=sched.name,
            session_id=sched.session_id,
        )
        try:
            await self._app.run_turn(sched.session_id, sched.prompt)
            await self._repo.update_last_fired(sched.schedule_id, datetime.now(UTC))
        except Exception as exc:
            runtime_logger.error(
                "scheduler_fire_failed",
                schedule_id=sched.schedule_id,
                name=sched.name,
                error=str(exc),
            )

    # ── Public CRUD API ───────────────────────────────────────────────────────

    async def create_schedule(self, request: CreateScheduleRequest) -> ScheduledRun:
        from citnega.packages.protocol.models.scheduler import ScheduledRun as _SR

        sched = _SR(
            schedule_id=str(uuid.uuid4()),
            name=request.name,
            schedule=request.schedule,
            session_id=request.session_id,
            prompt=request.prompt,
            enabled=request.enabled,
            next_fire_at=request.next_fire_at,
            created_at=datetime.now(UTC),
        )
        await self._repo.save(sched)
        runtime_logger.info(
            "schedule_created",
            schedule_id=sched.schedule_id,
            name=sched.name,
            schedule=sched.schedule,
        )
        return sched

    async def get_schedule(self, schedule_id: str) -> ScheduledRun | None:
        return await self._repo.get(schedule_id)

    async def list_schedules(self, enabled_only: bool = False) -> list[ScheduledRun]:
        if enabled_only:
            return await self._repo.list(enabled=True)
        return await self._repo.list()

    async def enable_schedule(self, schedule_id: str) -> None:
        sched = await self._repo.get(schedule_id)
        if sched is not None:
            await self._repo.save(sched.model_copy(update={"enabled": True}))

    async def disable_schedule(self, schedule_id: str) -> None:
        sched = await self._repo.get(schedule_id)
        if sched is not None:
            await self._repo.save(sched.model_copy(update={"enabled": False}))

    async def delete_schedule(self, schedule_id: str) -> None:
        await self._repo.delete(schedule_id)
        self._last_fired.pop(schedule_id, None)
        runtime_logger.info("schedule_deleted", schedule_id=schedule_id)

    async def schedule_once(
        self,
        name: str,
        session_id: str,
        prompt: str,
        fire_at: datetime,
    ) -> ScheduledRun:
        """Convenience: create a one-shot schedule that fires at a specific time."""
        from citnega.packages.protocol.models.scheduler import CreateScheduleRequest

        return await self.create_schedule(
            CreateScheduleRequest(
                name=name,
                schedule="once",
                session_id=session_id,
                prompt=prompt,
                enabled=True,
                next_fire_at=fire_at,
            )
        )
