"""StreamingBlock — live-updating assistant message during token streaming."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label, Markdown, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class StreamingBlock(Widget):
    """
    In-progress assistant response that grows one token at a time.

    Lifecycle:
      1. Tokens arrive → ``append_token(token)`` updates a plain ``Static``
         for fast, low-overhead rendering.
      2. ``finalize()`` replaces the ``Static`` with ``Markdown`` so the
         final response is properly formatted.

    Click to focus; Ctrl+Y copies the full buffered content.
    """

    can_focus = True

    DEFAULT_CSS = """
    StreamingBlock {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 1 1 1;
        border-left: thick $success;
        border-top: solid $panel-lighten-1;
        background: $surface;
    }
    StreamingBlock:focus {
        border: dashed $accent-darken-1;
        background: $boost;
        outline: none;
    }
    StreamingBlock .role-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }
    StreamingBlock .role-label {
        color: $success;
        text-style: bold;
        width: 1fr;
    }
    StreamingBlock .timestamp {
        color: $text-disabled;
        text-style: dim;
        content-align: right middle;
    }
    StreamingBlock .stream-text {
        height: auto;
        margin: 0;
        padding: 0;
    }
    StreamingBlock .cursor {
        color: $success;
        text-style: blink;
        height: 1;
    }
    StreamingBlock Markdown {
        height: auto;
        margin: 0;
        padding: 0;
        background: transparent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer = ""
        self._finalized = False
        self._token_count = 0
        self._timestamp = datetime.now().strftime("%H:%M")

    def on_click(self) -> None:
        """Clicking the block focuses it so Ctrl+Y can copy it."""
        self.focus()

    def compose(self) -> ComposeResult:
        with Horizontal(classes="role-header"):
            yield Label("◈ citnega", classes="role-label", id="role-label")
            yield Label(self._timestamp, classes="timestamp", id="stream-ts")
        yield Static("", id="stream-text", classes="stream-text", markup=False)
        yield Label("▌", classes="cursor", id="stream-cursor")

    def append_token(self, token: str) -> None:
        self._buffer += token
        self._token_count += len(token.split())
        with contextlib.suppress(Exception):
            self.query_one("#stream-text", Static).update(self._buffer)
        with contextlib.suppress(Exception):
            self.query_one("#role-label", Label).update(
                f"◈ citnega  {self._token_count}t"
            )

    async def finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        with contextlib.suppress(Exception):
            self.query_one("#stream-cursor", Label).display = False
        try:
            plain = self.query_one("#stream-text", Static)
            await plain.remove()
        except Exception:
            pass
        await self.mount(Markdown(self._buffer.strip() or "", id="stream-md"))
        with contextlib.suppress(Exception):
            self.scroll_visible(animate=False)

    @property
    def text(self) -> str:
        return self._buffer
