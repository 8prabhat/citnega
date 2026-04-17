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


def _build_bar_content(
    *,
    model: str,
    mode: str,
    think: str,
    folder: str,
    state: str,
    session_name: str,
    tokens_used: int,
    tokens_max: int,
    spin_char: str,
    session_id: str = "",
    framework: str = "",
) -> str:
    model_str = model or "no model"
    mode_str  = mode or "direct"

    folder_str = folder or os.getcwd()
    home = os.path.expanduser("~")
    if folder_str.startswith(home):
        folder_str = "~" + folder_str[len(home):]
    if len(folder_str) > 28:
        folder_str = "…" + folder_str[-25:]

    if state in _ACTIVE_STATES:
        state_label = f"{spin_char} {state.replace('_', ' ')}"
    else:
        state_label = _STATE_LABELS.get(state, state)

    if tokens_max > 0:
        ratio = tokens_used / tokens_max
        tok_indicator = "▓" if ratio >= 0.8 else ("▒" if ratio >= 0.5 else "░")
        token_str = f"{tok_indicator} {tokens_used}/{tokens_max}"
    else:
        token_str = ""

    sep = "  │  "
    parts: list[str] = []

    # Session badge: prefer name, fall back to short ID
    badge = session_name[:18] if session_name else (f"#{session_id[:8]}" if session_id else "")
    if badge:
        parts.append(badge)

    # Model + framework
    fw_suffix = f"/{framework}" if framework and framework != "direct" else ""
    parts.append(f"◈ {model_str}{fw_suffix}")

    parts.append(f"mode:{mode_str}")

    if think and think != "off":
        parts.append(f"think:{think}")

    parts.append(folder_str)

    if token_str:
        parts.append(token_str)

    parts.append(state_label)
    return sep.join(parts)


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
    session_name: reactive[str] = reactive("")
    tokens_used: reactive[int] = reactive(0)
    tokens_max: reactive[int] = reactive(0)
    session_id: reactive[str] = reactive("")
    framework: reactive[str] = reactive("")

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
        content = _build_bar_content(
            model=self.model,
            mode=self.mode,
            think=self.think,
            folder=self.folder,
            state=self.state,
            session_name=self.session_name,
            tokens_used=self.tokens_used,
            tokens_max=self.tokens_max,
            spin_char=_SPINNER[self._spin_idx],
            session_id=self.session_id,
            framework=self.framework,
        )
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

    def watch_session_name(self, _: str) -> None:
        self._redraw()

    def watch_tokens_used(self, _: int) -> None:
        self._redraw()

    def watch_tokens_max(self, _: int) -> None:
        self._redraw()

    def watch_session_id(self, _: str) -> None:
        self._redraw()

    def watch_framework(self, _: str) -> None:
        self._redraw()
