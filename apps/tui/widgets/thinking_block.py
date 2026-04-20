"""ThinkingBlock — inline chain-of-thought, same visual language as tool/agent calls."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Click
    from textual.timer import Timer

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_BULLET   = "◇"   # hollow — internal reasoning, not an external action


def _elapsed_str(seconds: float) -> str:
    if seconds < 1.0:
        return f"[{int(seconds * 1000)}ms]"
    return f"[{seconds:.1f}s]"


class ThinkingBlock(Widget):
    """
    Inline thinking block — same compact style as ToolCallBlock / AgentCallBlock.

    While streaming:
        ◇  ⠸  thinking…  [0.3s]          (warning colour — brain is working)

    Finalised (click header to expand):
        ◇  ↯  thinking  2847 chars  [1.2s]  (dimmed — done, expand if curious)
        │  ... chain of thought text ...

    Lifecycle::

        block = ThinkingBlock()
        await scroll.mount(block)
        block.append_token("…token…")   # per ThinkingEvent
        block.finalize()                # when thinking ends
    """

    DEFAULT_CSS = """
    ThinkingBlock {
        height: auto;
        padding: 0;
    }

    ThinkingBlock Label#th-header {
        height: 1;
        padding: 0 0 0 1;
        color: $warning;
    }
    ThinkingBlock Label#th-header:hover {
        background: $boost;
    }

    /* After finalization: dim the header — reasoning is done */
    ThinkingBlock.done Label#th-header {
        color: $text-disabled;
    }

    /* When connected to the immediately-following tool call: collapse bottom gap */
    ThinkingBlock.-connected {
        margin-bottom: 0;
        padding-bottom: 0;
    }

    /* Expanded body */
    ThinkingBlock Static#th-body {
        display: none;
        height: auto;
        padding: 0 1 1 1;
        margin: 0 0 0 3;
        border-left: solid $warning-darken-2;
        color: $text-muted;
        text-style: italic;
    }
    ThinkingBlock.-expanded Static#th-body {
        display: block;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer = ""
        self._finalized = False
        self._start: float = 0.0
        self._spin_idx: int = 0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Label(
            f"{_BULLET}  {_SPINNER[0]}  thinking…",
            id="th-header",
        )
        yield Static("", id="th-body", markup=False)

    def on_mount(self) -> None:
        self._start = time.monotonic()
        self._timer = self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        if self._finalized:
            return
        self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
        spin = _SPINNER[self._spin_idx]
        elapsed = _elapsed_str(time.monotonic() - self._start)
        with contextlib.suppress(Exception):
            self.query_one("#th-header", Label).update(
                f"{_BULLET}  {spin}  thinking…  {elapsed}"
            )

    def _stop_timer(self) -> None:
        if self._timer is not None:
            with contextlib.suppress(Exception):
                self._timer.stop()
            self._timer = None

    def append_token(self, token: str) -> None:
        """Stream one reasoning token in (called from event loop)."""
        self._buffer += token
        with contextlib.suppress(Exception):
            self.query_one("#th-body", Static).update(self._buffer)

    def finalize(self) -> None:
        """Mark thinking complete — update header with char count."""
        if self._finalized:
            return
        self._finalized = True
        self._stop_timer()
        elapsed = _elapsed_str(time.monotonic() - self._start)
        char_count = len(self._buffer)
        self.add_class("done")
        with contextlib.suppress(Exception):
            self.query_one("#th-header", Label).update(
                f"{_BULLET}  ↯  thinking  {char_count:,} chars  {elapsed}"
            )
        with contextlib.suppress(Exception):
            self.query_one("#th-body", Static).update(self._buffer)

    def connect_to_next(self) -> None:
        """Remove bottom gap so the next tool call feels directly caused by this thinking."""
        self.add_class("-connected")

    def on_click(self, event: Click) -> None:
        if self._finalized and self._buffer:
            self.toggle_class("-expanded")

    @property
    def has_content(self) -> bool:
        return bool(self._buffer)
