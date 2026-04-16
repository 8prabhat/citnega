"""ContextBar — compact one-line info strip above the SmartInput.

Shows the user at a glance:
  ◈ model-name  │  mode: direct  │  think: off  │  ~/workfolder  │  ⠼ executing

Reactive fields are updated by ChatController as session state changes.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Human-readable labels for run states
_STATE_LABELS: dict[str, str] = {
    "idle":                "●  idle",
    "pending":             "○  starting",
    "context_assembling":  "⠿  assembling context",
    "executing":           "⠿  executing",
    "waiting_approval":    "⚠  waiting approval",
    "paused":              "⏸  paused",
    "completed":           "●  idle",
    "failed":              "✗  failed",
    "cancelled":           "✗  cancelled",
    "running":             "⠿  running",
}

_ACTIVE_STATES = {"pending", "context_assembling", "executing", "running"}


class ContextBar(Widget):
    """
    Single-line context strip rendered just above the SmartInput.

    Animated spinner on the state segment while a run is active.
    All fields are updated externally by ChatController.
    """

    DEFAULT_CSS = """
    ContextBar {
        height: 1;
        background: $panel-darken-1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    model: reactive[str] = reactive("")
    mode: reactive[str] = reactive("direct")
    think: reactive[str] = reactive("off")
    folder: reactive[str] = reactive("")
    state: reactive[str] = reactive("idle")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._spin_idx: int = 0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Label("", id="cb-content")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.12, self._tick)
        self._redraw()

    def _tick(self) -> None:
        if self.state in _ACTIVE_STATES:
            self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
        self._redraw()

    def _redraw(self) -> None:
        model_str = self.model or "no model"
        mode_str  = self.mode or "direct"
        think_str = self.think or "off"

        folder_str = self.folder or os.getcwd()
        home = os.path.expanduser("~")
        if folder_str.startswith(home):
            folder_str = "~" + folder_str[len(home):]
        # Truncate long paths from the left
        if len(folder_str) > 30:
            folder_str = "…" + folder_str[-27:]

        # State segment — animated when active
        state_key = self.state
        if state_key in _ACTIVE_STATES:
            spin = _SPINNER[self._spin_idx]
            state_label = f"{spin}  {state_key.replace('_', ' ')}"
        else:
            state_label = _STATE_LABELS.get(state_key, state_key)

        sep = "  │  "
        parts = [
            f"◈ {model_str}",
            f"mode: {mode_str}",
            f"think: {think_str}",
            folder_str,
            state_label,
        ]
        content = sep.join(parts)

        with contextlib.suppress(Exception):
            self.query_one("#cb-content", Label).update(content)

    # ── Reactive watchers — any change redraws immediately ────────────────────

    def watch_model(self, _: str) -> None:
        self._redraw()

    def watch_mode(self, _: str) -> None:
        self._redraw()

    def watch_think(self, _: str) -> None:
        self._redraw()

    def watch_folder(self, _: str) -> None:
        self._redraw()

    def watch_state(self, _: str) -> None:
        self._spin_idx = 0
        self._redraw()
