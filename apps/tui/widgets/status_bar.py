"""StatusBar — bottom status line for the TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label


class StatusBar(Widget):
    """
    One-line status bar rendered at the bottom of ChatScreen.

    Reactive fields:
      session_id  — displayed as "session: <id[:8]>"
      framework   — active framework adapter name
      run_state   — current run state (idle / running / waiting…)
      model       — active model id
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
        layout: horizontal;
    }
    StatusBar .status-session { width: 1fr; }
    StatusBar .status-state   { width: 1fr; content-align: center middle; }
    StatusBar .status-model   { width: 1fr; content-align: right middle; }
    """

    session_id: reactive[str] = reactive("—")
    framework:  reactive[str] = reactive("direct")
    run_state:  reactive[str] = reactive("idle")
    model:      reactive[str] = reactive("")
    mode:       reactive[str] = reactive("")   # e.g. "[PLAN]" or ""

    def compose(self) -> ComposeResult:
        yield Label("", id="status-session", classes="status-session")
        yield Label("", id="status-state",   classes="status-state")
        yield Label("", id="status-model",   classes="status-model")

    def watch_session_id(self, value: str) -> None:
        short = value[:8] if len(value) > 8 else value
        self.query_one("#status-session", Label).update(f"session: {short}")

    def watch_framework(self, value: str) -> None:
        self._refresh_state()

    def watch_run_state(self, value: str) -> None:
        self._refresh_state()

    def watch_mode(self, value: str) -> None:
        self._refresh_state()

    def watch_model(self, value: str) -> None:
        label = self.query_one("#status-model", Label)
        label.update(f"model: {value}" if value else "")

    def set_model(self, model_id: str) -> None:
        self.model = model_id

    def set_mode(self, mode_label: str) -> None:
        self.mode = mode_label

    def _refresh_state(self) -> None:
        parts = [self.framework, self.run_state]
        if self.mode:
            parts.append(self.mode)
        self.query_one("#status-state", Label).update(" | ".join(parts))
