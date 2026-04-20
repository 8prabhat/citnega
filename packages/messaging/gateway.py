"""
Messaging gateway — IMessagingChannel interface and MessagingGateway router.

IMessagingChannel is an interface with Telegram and Discord implementations.
MessagingGateway holds multiple channels and broadcasts to all of them.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class IMessagingChannel(ABC):
    """Contract for a messaging backend (Telegram, Discord, etc.)."""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique name for this channel (e.g. 'telegram', 'discord')."""
        ...

    @abstractmethod
    async def send(self, text: str, chat_id: str | None = None) -> None:
        """Send a text message. chat_id overrides the configured default."""
        ...

    @abstractmethod
    async def start_polling(
        self, on_message: Callable[[str, str], Awaitable[None]]
    ) -> None:
        """
        Start receiving incoming messages.

        on_message(chat_id, text) is called for each message received.
        Runs until stop() is called.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop polling and clean up resources."""
        ...


class MessagingGateway:
    """Routes outgoing messages to all registered channels."""

    def __init__(self, channels: list[IMessagingChannel]) -> None:
        self._channels = {c.channel_name: c for c in channels}

    async def broadcast(self, text: str) -> None:
        """Send text to all channels. Errors in individual channels are swallowed."""
        if not self._channels:
            return
        await asyncio.gather(
            *[c.send(text) for c in self._channels.values()],
            return_exceptions=True,
        )

    async def send_to(self, channel_name: str, text: str, chat_id: str | None = None) -> None:
        """Send to a specific channel by name. No-op if channel not registered."""
        channel = self._channels.get(channel_name)
        if channel:
            await channel.send(text, chat_id=chat_id)

    @property
    def active_channels(self) -> list[str]:
        return list(self._channels.keys())
