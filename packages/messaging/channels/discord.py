"""
Discord messaging channel.

Optional dependency: discord.py>=2.3
Install: pip install discord.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from citnega.packages.messaging.gateway import IMessagingChannel

if TYPE_CHECKING:
    from citnega.packages.config.settings import DiscordSettings


class DiscordChannel(IMessagingChannel):
    """Sends and receives messages via a Discord bot."""

    @property
    def channel_name(self) -> str:
        return "discord"

    def __init__(self, settings: DiscordSettings) -> None:
        self._settings = settings
        self._client: object = None
        self._stop_event: asyncio.Event = asyncio.Event()

    def _get_token(self) -> str:
        token = self._settings.bot_token.get_secret_value()
        if not token:
            raise RuntimeError("Discord bot_token is not configured")
        return token

    async def send(self, text: str, chat_id: str | None = None) -> None:
        try:
            import discord  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("discord.py not installed: pip install discord.py") from exc

        channel_id_str = chat_id or self._settings.default_channel_id
        if not channel_id_str:
            raise RuntimeError("Discord: no channel_id provided and default_channel_id not configured")

        channel_id = int(channel_id_str)
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready() -> None:  # type: ignore[misc]
            ch = await client.fetch_channel(channel_id)
            # Discord message limit is 2000 chars
            for chunk_start in range(0, len(text), 2000):
                await ch.send(text[chunk_start : chunk_start + 2000])
            await client.close()

        await client.start(self._get_token())

    async def start_polling(
        self, on_message: Callable[[str, str], Awaitable[None]]
    ) -> None:
        try:
            import discord  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("discord.py not installed: pip install discord.py") from exc

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client
        self._stop_event.clear()

        @client.event
        async def on_message(message: object) -> None:  # type: ignore[misc]
            if getattr(message, "author", None) == client.user:
                return
            ch_id = str(getattr(message.channel, "id", ""))
            content = getattr(message, "content", "")
            if content:
                await on_message(ch_id, content)

        await client.start(self._get_token())

    async def stop(self) -> None:
        if self._client is not None:
            import contextlib
            with contextlib.suppress(Exception):
                await self._client.close()  # type: ignore[attr-defined]
            self._client = None
