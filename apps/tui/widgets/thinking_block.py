"""ThinkingBlock — collapsible widget that shows the model's reasoning."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Collapsible, Static


class ThinkingBlock(Widget):
    """
    A collapsible block that streams the model's chain-of-thought in real time.

    Collapsed by default — users can open it to inspect the reasoning.
    The title updates when thinking is complete to show the character count.

    Lifecycle::

        block = ThinkingBlock()
        await scroll.mount(block)
        block.append_token("…thinking token…")   # called per ThinkingEvent
        block.finalize()                          # called when thinking ends
    """

    DEFAULT_CSS = """
    ThinkingBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $warning;
        background: $panel;
    }
    ThinkingBlock Collapsible {
        height: auto;
        background: transparent;
        border: none;
        padding: 0;
    }
    ThinkingBlock .thinking-content {
        height: auto;
        color: $text-muted;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer    = ""
        self._finalized = False

    def compose(self) -> ComposeResult:
        with Collapsible(title="Thinking…", collapsed=True, id="thinking-collapsible"):
            yield Static(
                "",
                id="thinking-content",
                classes="thinking-content",
                markup=False,
            )

    # ── Streaming ─────────────────────────────────────────────────────────────

    def append_token(self, token: str) -> None:
        """Append one reasoning token to the display (called from event loop)."""
        self._buffer += token
        try:
            self.query_one("#thinking-content", Static).update(self._buffer)
        except Exception:
            pass

    def finalize(self) -> None:
        """
        Mark thinking as complete.

        Updates the collapsible title to show the character count so the user
        knows how much reasoning was produced without having to expand it.
        """
        if self._finalized:
            return
        self._finalized = True
        try:
            coll = self.query_one("#thinking-collapsible", Collapsible)
            char_count = len(self._buffer)
            coll.title = f"Thinking ({char_count} chars) — click to expand"
        except Exception:
            pass
        # Ensure final content is shown if expanded
        try:
            self.query_one("#thinking-content", Static).update(self._buffer)
        except Exception:
            pass

    @property
    def has_content(self) -> bool:
        return bool(self._buffer)
