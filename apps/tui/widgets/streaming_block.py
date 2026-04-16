"""StreamingBlock — live-updating assistant message during token streaming."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

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
        margin: 0 0 1 0;
        padding: 0 1 1 1;
        border-left: thick $success;
        background: $surface;
    }
    StreamingBlock:focus {
        border: dashed $accent-darken-1;
        background: $boost;
        outline: none;
    }
    StreamingBlock .role-label {
        color: $success;
        text-style: bold;
        height: 1;
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

    def on_click(self) -> None:
        """Clicking the block focuses it so Ctrl+Y can copy it."""
        self.focus()

    def compose(self) -> ComposeResult:
        yield Label("Citnega", classes="role-label")
        yield Static("", id="stream-text", classes="stream-text", markup=False)
        yield Label("▌", classes="cursor", id="stream-cursor")

    def append_token(self, token: str) -> None:
        self._buffer += token
        with contextlib.suppress(Exception):
            self.query_one("#stream-text", Static).update(self._buffer)

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
        md_content = self._buffer.strip() or "(empty response)"
        await self.mount(Markdown(md_content, id="stream-md"))
        with contextlib.suppress(Exception):
            self.scroll_visible(animate=False)

    @property
    def text(self) -> str:
        return self._buffer
