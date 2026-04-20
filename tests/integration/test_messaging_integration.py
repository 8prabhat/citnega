"""Integration tests: MessagingGateway and HeartbeatEngine."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_broadcast_calls_all_channels() -> None:
    from citnega.packages.messaging.gateway import MessagingGateway

    ch1 = MagicMock()
    ch1.channel_name = "test1"
    ch1.send = AsyncMock()
    ch2 = MagicMock()
    ch2.channel_name = "test2"
    ch2.send = AsyncMock()

    gw = MessagingGateway([ch1, ch2])
    await gw.broadcast("hello")

    ch1.send.assert_awaited_once_with("hello")
    ch2.send.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_broadcast_swallows_channel_errors() -> None:
    from citnega.packages.messaging.gateway import MessagingGateway

    ch = MagicMock()
    ch.channel_name = "failing"
    ch.send = AsyncMock(side_effect=RuntimeError("channel down"))

    gw = MessagingGateway([ch])
    # Should not raise
    await gw.broadcast("hello")


@pytest.mark.asyncio
async def test_send_to_specific_channel() -> None:
    from citnega.packages.messaging.gateway import MessagingGateway

    ch1 = MagicMock()
    ch1.channel_name = "telegram"
    ch1.send = AsyncMock()
    ch2 = MagicMock()
    ch2.channel_name = "discord"
    ch2.send = AsyncMock()

    gw = MessagingGateway([ch1, ch2])
    await gw.send_to("telegram", "ping")

    ch1.send.assert_awaited_once_with("ping", chat_id=None)
    ch2.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_skips_when_no_file(tmp_path: Path) -> None:
    from citnega.packages.messaging.gateway import MessagingGateway
    from citnega.packages.messaging.heartbeat import HeartbeatEngine

    gw = MagicMock(spec=MessagingGateway)
    gw.broadcast = AsyncMock()
    engine = HeartbeatEngine(workfolder=tmp_path, gateway=gw, app_service=None)

    await engine._check_schedules()
    gw.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_fires_when_schedule_matches(tmp_path: Path) -> None:
    from citnega.packages.messaging.gateway import MessagingGateway
    from citnega.packages.messaging.heartbeat import HeartbeatEngine

    hb_file = tmp_path / "heartbeat.md"
    # "* * * * *" always matches — message-only heartbeat (no prompt/app_service)
    hb_file.write_text(
        "---\nheartbeats:\n  - name: test\n    schedule: \"* * * * *\"\n    channel: all\n---\n"
    )

    gw = MagicMock(spec=MessagingGateway)
    gw.broadcast = AsyncMock()
    engine = HeartbeatEngine(workfolder=tmp_path, gateway=gw, app_service=None)

    await engine._check_schedules()
    gw.broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_start_stop() -> None:
    from citnega.packages.messaging.gateway import MessagingGateway
    from citnega.packages.messaging.heartbeat import HeartbeatEngine

    gw = MagicMock(spec=MessagingGateway)
    gw.broadcast = AsyncMock()
    engine = HeartbeatEngine(workfolder=Path("/tmp"), gateway=gw, app_service=None)

    engine.start()
    assert engine._task is not None
    assert not engine._task.done()
    await engine.stop()
    assert engine._task.done()
