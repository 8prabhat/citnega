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
    An in-progress assistant response that grows one token at a time.

    Streaming lifecycle:
      1. Tokens arrive → ``append_token(token)`` updates a plain ``Static``
         for fast, low-overhead rendering.
      2. ``finalize()`` is called when the run completes.  The plain ``Static``
         is replaced by a ``Markdown`` widget so the final response is
         properly formatted (code blocks, bold, lists, etc.).

    Both methods must be called from within the Textual event loop.
    ``finalize()`` is an async method so the controller must await it.
    """

    DEFAULT_CSS = """
    StreamingBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $success;
        background: $surface;
    }
    StreamingBlock .role-label {
        color: $text-muted;
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

    def compose(self) -> ComposeResult:
        yield Label("Citnega", classes="role-label")
        yield Static("", id="stream-text", classes="stream-text", markup=False)
        yield Label("▌", classes="cursor", id="stream-cursor")

    # ── Called during streaming ───────────────────────────────────────────────

    def append_token(self, token: str) -> None:
        """Append a token to the live plain-text display."""
        self._buffer += token
        try:
            self.query_one("#stream-text", Static).update(self._buffer)
        except Exception:
            pass  # widget may not be mounted yet on the very first token

    # ── Called on run completion ──────────────────────────────────────────────

    async def finalize(self) -> None:
        """
        Replace the streaming ``Static`` with a rendered ``Markdown`` widget.

        Hides the blinking cursor and gives the response proper markdown
        formatting (fenced code blocks, bold/italic, lists, tables, etc.).
        """
        if self._finalized:
            return
        self._finalized = True

        # Hide the cursor
        with contextlib.suppress(Exception):
            self.query_one("#stream-cursor", Label).display = False

        # Swap plain-text widget → Markdown renderer
        try:
            plain = self.query_one("#stream-text", Static)
            await plain.remove()
        except Exception:
            pass

        md_content = self._buffer.strip() or "(empty response)"
        await self.mount(Markdown(md_content, id="stream-md"))

        # Scroll parent to show the fully rendered block
        with contextlib.suppress(Exception):
            self.scroll_visible(animate=False)

    @property
    def text(self) -> str:
        return self._buffer
