"""
CancellationToken — cooperative cancellation for framework runners.

Framework runners poll ``is_cancelled()`` at yield points rather than
relying solely on asyncio.CancelledError.  This lets adapters implement
graceful shutdown that drains in-flight tool calls before stopping.
"""

from __future__ import annotations

import asyncio


class CancellationToken:
    """
    A lightweight cooperative-cancellation flag.

    Usage::

        token = CancellationToken()
        # In producer (CoreRuntime):
        token.cancel()
        # In consumer (framework runner):
        if token.is_cancelled():
            break
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        """Signal cancellation."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._event.is_set()

    async def wait(self) -> None:
        """Suspend until cancellation is signalled."""
        await self._event.wait()
