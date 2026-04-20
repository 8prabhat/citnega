"""
HeartbeatEngine — proactive scheduled messages driven by workfolder/heartbeat.md.

Format of workfolder/heartbeat.md:
---
heartbeats:
  - name: morning_standup
    schedule: "0 9 * * 1-5"    # cron: weekdays at 9am
    channel: telegram            # or 'discord' or 'all'
    prompt: "What are today's priorities based on recent work?"
    session_id: "heartbeat-standup"
---

Cron support: minute hour dom month dow (5-field, no seconds).
All numeric — no named months/weekdays in this minimal implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from citnega.packages.messaging.gateway import MessagingGateway


def _cron_matches(schedule: str, now: datetime) -> bool:
    """Return True if cron schedule matches the current minute."""
    fields = schedule.strip().split()
    if len(fields) != 5:
        return False
    minute_s, hour_s, _dom_s, _month_s, dow_s = fields

    def _matches(field: str, value: int) -> bool:
        if field == "*":
            return True
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


class HeartbeatEngine:
    """Reads workfolder/heartbeat.md and fires scheduled prompts via MessagingGateway."""

    _CHECK_INTERVAL = 60  # seconds between schedule checks

    def __init__(
        self,
        workfolder: Path,
        gateway: MessagingGateway,
        app_service: Any = None,
    ) -> None:
        self._workfolder = workfolder
        self._gateway = gateway
        self._app = app_service
        self._task: asyncio.Task[None] | None = None
        self._last_fired: dict[str, str] = {}  # name → "YYYY-MM-DD HH:MM"

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="heartbeat_engine")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._CHECK_INTERVAL)
            with contextlib.suppress(Exception):
                await self._check_schedules()

    async def _check_schedules(self) -> None:
        hb_file = self._workfolder / "heartbeat.md"
        if not hb_file.exists():
            return

        try:
            import yaml  # type: ignore[import]
        except ImportError:
            return  # PyYAML is a core dep — should always be available

        text = hb_file.read_text(encoding="utf-8")
        # Extract YAML front matter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                front = parts[1]
            else:
                return
        else:
            front = text

        try:
            config = yaml.safe_load(front) or {}
        except Exception:
            return

        now = datetime.now(UTC)
        minute_key = now.strftime("%Y-%m-%d %H:%M")

        for hb in config.get("heartbeats", []):
            name = hb.get("name", "unnamed")
            schedule = hb.get("schedule", "")
            if not schedule:
                continue
            if not _cron_matches(schedule, now):
                continue
            if self._last_fired.get(name) == minute_key:
                continue  # already fired this minute

            self._last_fired[name] = minute_key
            await self._fire(hb)

    async def _fire(self, hb: dict[str, Any]) -> None:
        prompt = hb.get("prompt", "")
        session_id = hb.get("session_id", "heartbeat")
        channel = hb.get("channel", "all")
        name = hb.get("name", "heartbeat")

        message = f"[Heartbeat: {name}]\n"

        # If we have an app service and a prompt, run an agent turn
        if prompt and self._app is not None:
            try:
                result = await asyncio.wait_for(
                    self._app.run_turn(session_id, prompt),
                    timeout=120,
                )
                message += result if isinstance(result, str) else str(result)
            except Exception as exc:
                message += f"Error running heartbeat prompt: {exc}"
        elif prompt:
            message += prompt
        else:
            message += "Scheduled heartbeat."

        if channel == "all":
            await self._gateway.broadcast(message)
        else:
            await self._gateway.send_to(channel, message)
