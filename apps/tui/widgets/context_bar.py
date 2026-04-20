"""ContextBar — two-line info strip at the bottom of the TUI.

Line 1 (live session state):
  session │ ◈ model/fw │ mode:X │ think:X │ ~/folder │ tokens │ ⠼ state

Line 2 (static config — no overlap with line 1):
  ⚙ CFG │ rounds:5 │ depth:2 │ local:on │ policy:dev │ retries:3/2 │ compact:on @50msg │ cb:5 │ F2=edit

Reactive fields are updated by ChatController as session state changes.
Call refresh_config() after settings are saved to update line 2.
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


def _build_state_line(
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
        color = "red" if ratio >= 0.8 else ("yellow" if ratio >= 0.5 else "green")
        token_str = f"[{color}]{tok_indicator} {tokens_used}/{tokens_max}[/{color}]"
    else:
        token_str = ""

    sep = "  │  "
    parts: list[str] = []

    badge = session_name[:18] if session_name else (f"#{session_id[:8]}" if session_id else "")
    if badge:
        parts.append(badge)

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


def _bool_label(value: bool) -> str:
    return "[green]on[/green]" if value else "[dim]off[/dim]"


def _build_config_line() -> str:
    """Return compact one-line config strip (no overlap with state line)."""
    sep = "  [dim]│[/dim]  "

    max_rounds = 5
    depth = 2
    local_only = True
    policy = "dev"
    retries = 3
    s_retries = 2
    auto_compact = True
    compact_at = 50
    cb_thresh = 5
    bypass_perms = False

    try:
        from citnega.packages.config.loaders import load_settings
        s = load_settings()
        max_rounds    = s.runtime.max_tool_rounds
        depth         = s.runtime.max_callable_depth
        local_only    = s.runtime.local_only
        policy        = s.policy.template
        retries       = s.runtime.provider_max_retries
        s_retries     = s.runtime.streaming_max_retries
        auto_compact  = s.conversation.auto_compact
        compact_at    = s.conversation.compact_threshold_messages
        cb_thresh     = s.runtime.circuit_breaker_threshold
        bypass_perms  = s.policy.bypass_permissions
    except Exception:
        pass

    compact_str = _bool_label(auto_compact)
    if auto_compact and compact_at > 0:
        compact_str += f" @{compact_at}msg"

    parts = [
        "[bold dim]⚙ CFG[/bold dim]",
        f"rounds:{max_rounds}",
        f"depth:{depth}",
        f"local:{_bool_label(local_only)}",
        f"policy:{policy}",
        f"retries:{retries}/{s_retries}",
        f"compact:{compact_str}",
        f"cb:{cb_thresh}",
    ]

    bypass_str = "[bold red]⚠ ON[/bold red]" if bypass_perms else "[dim]off[/dim]"
    parts.append(f"bypass:{bypass_str}")

    parts.append("[dim]F2=edit[/dim]")
    return sep.join(parts)


class ContextBar(Widget):
    """
    Two-line strip: live session state (line 1) + static config (line 2).

    Line 1 animates while a run is active.
    Call refresh_config() after saving settings to update line 2 immediately.
    """

    DEFAULT_CSS = """
    ContextBar {
        height: 2;
        background: $panel-darken-1;
        color: $text-muted;
        padding: 0 1;
    }

    #cb-state {
        height: 1;
        background: $panel-darken-2;
        color: $text-muted;
    }

    #cb-config {
        height: 1;
        background: $panel-darken-1;
        color: $text-disabled;
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
        yield Label("", id="cb-state")
        yield Label("", id="cb-config")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.12, self._tick)
        self._redraw()
        self.refresh_config()

    def _tick(self) -> None:
        if self.state in _ACTIVE_STATES:
            self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
        self._redraw()

    def _redraw(self) -> None:
        content = _build_state_line(
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
            self.query_one("#cb-state", Label).update(content)

    def refresh_config(self) -> None:
        """Re-read settings and update the config line."""
        with contextlib.suppress(Exception):
            line = _build_config_line()
            self.query_one("#cb-config", Label).update(line)

    # ── Reactive watchers ────────────────────────────────────────────────────

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
