"""
Telegram messaging channel.

Optional dependency: python-telegram-bot>=21.0
Install: pip install python-telegram-bot
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from citnega.packages.messaging.gateway import IMessagingChannel

if TYPE_CHECKING:
    from citnega.packages.config.settings import TelegramSettings


class TelegramChannel(IMessagingChannel):
    """Sends and receives messages via a Telegram bot."""

    @property
    def channel_name(self) -> str:
        return "telegram"

    def __init__(self, settings: TelegramSettings) -> None:
        self._settings = settings
        self._app: object = None

    def _get_token(self) -> str:
        token = self._settings.bot_token.get_secret_value()
        if not token:
            raise RuntimeError("Telegram bot_token is not configured")
        return token

    async def send(self, text: str, chat_id: str | None = None) -> None:
        try:
            from telegram import Bot  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "python-telegram-bot not installed: pip install python-telegram-bot"
            ) from exc

        target = chat_id or self._settings.default_chat_id
        if not target:
            raise RuntimeError("Telegram: no chat_id provided and default_chat_id not configured")

        async with Bot(token=self._get_token()) as bot:
            # Telegram message limit is 4096 chars
            for chunk_start in range(0, len(text), 4096):
                await bot.send_message(
                    chat_id=target,
                    text=text[chunk_start : chunk_start + 4096],
                )

    async def start_polling(
        self, on_message: Callable[[str, str], Awaitable[None]]
    ) -> None:
        try:
            from telegram.ext import Application, MessageHandler, filters  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "python-telegram-bot not installed: pip install python-telegram-bot"
            ) from exc

        async def _handler(update: object, ctx: object) -> None:
            msg = getattr(update, "message", None)
            if msg and hasattr(msg, "text") and msg.text:
                chat_id = str(msg.chat_id)
                await on_message(chat_id, msg.text)

        self._app = Application.builder().token(self._get_token()).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handler))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        if self._app is not None:
            import contextlib
            with contextlib.suppress(Exception):
                await self._app.updater.stop()  # type: ignore[attr-defined]
                await self._app.stop()
                await self._app.shutdown()
            self._app = None
