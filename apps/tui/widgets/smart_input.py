"""
SmartInput — full-height multiline prompt panel for the chat screen.

Features
--------
- **Multiline TextArea**: real multi-line editing, word-wrap, scrollable.
- **Ctrl+Enter**: submit (Enter adds a newline as in any editor).
- **Alt+↑ / Alt+↓**: history navigation (↑↓ move the cursor within the text).
- **Command history**: last N entries, configurable via settings.
"""

from __future__ import annotations

from collections import deque

from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea

_MAX_HISTORY_DEFAULT = 200


def _get_max_history() -> int:
    try:
        from citnega.packages.config.loaders import load_settings
        return load_settings().tui.input_history_size
    except Exception:
        return _MAX_HISTORY_DEFAULT


class SmartInput(Widget):
    """
    Multiline prompt panel (TextArea-backed).

    Submit via Ctrl+Enter.  Navigate history via Alt+↑ / Alt+↓.
    Up / Down move the text cursor within the current draft as expected.
    """

    class Submitted(Message):
        def __init__(self, input: "SmartInput") -> None:
            super().__init__()
            self.input = input

    class Changed(Message):
        def __init__(self, input: "SmartInput", value: str) -> None:
            super().__init__()
            self.input = input
            self.value = value

    DEFAULT_CSS = """
    SmartInput {
        height: auto;
        min-height: 6;
        max-height: 14;
        background: $surface;
        border-top: heavy $primary-darken-2;
        border-bottom: solid $panel-lighten-1;
    }

    SmartInput #hint-bar {
        height: 1;
        background: $panel-darken-1;
        color: $text-muted;
        padding: 0 2;
        text-align: right;
    }

    SmartInput TextArea {
        height: 1fr;
        min-height: 5;
        border: none;
        background: $surface;
        padding: 0 1;
    }

    SmartInput TextArea:focus {
        background: $boost;
        border: none;
    }
    """

    def __init__(self, placeholder: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._placeholder = placeholder
        self._history: deque[str] = deque(maxlen=_get_max_history())
        self._history_index: int = -1
        self._draft: str = ""

    def compose(self) -> ComposeResult:
        yield Static(
            "Ctrl+S send  •  Alt+↑↓ history  •  / for commands",
            id="hint-bar",
        )
        yield TextArea(
            soft_wrap=True,
            show_line_numbers=False,
            tab_behavior="indent",
        )

    def on_mount(self) -> None:
        self._textarea.focus()

    # ── Internal access ───────────────────────────────────────────────────────

    @property
    def _textarea(self) -> TextArea:
        return self.query_one(TextArea)

    # ── Public API (used by chat_screen, controller, slash commands) ──────────

    @property
    def value(self) -> str:
        return self._textarea.text

    @property
    def actual_value(self) -> str:
        return self.value

    @property
    def selected_text(self) -> str:
        try:
            return self._textarea.selected_text
        except Exception:
            return ""

    @property
    def is_input_focused(self) -> bool:
        try:
            return bool(self.app.focused is self._textarea)
        except Exception:
            return False

    def focus(self, scroll_visible: bool = True) -> "SmartInput":
        self._textarea.focus(scroll_visible)
        return self

    def seed_history(self, messages: list[str]) -> None:
        """Populate arrow-key history. Pass messages oldest-first."""
        self._history.clear()
        self._history_index = -1
        self._draft = ""
        for msg in messages:
            if msg:
                self._history.appendleft(msg)

    def submit_and_clear(self) -> str:
        """Consume the current value, push to history, clear the editor."""
        text = self.value.strip()
        if text:
            self._history.appendleft(text)
        self._history_index = -1
        self._draft = ""
        self._textarea.clear()
        return text

    # ── Key handling ──────────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+enter":
            self.post_message(self.Submitted(input=self))
            event.prevent_default()
            event.stop()
        elif event.key == "alt+up":
            self._history_up()
            event.prevent_default()
            event.stop()
        elif event.key == "alt+down":
            self._history_down()
            event.prevent_default()
            event.stop()

    # ── Forward TextArea.Changed as SmartInput.Changed ───────────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.post_message(self.Changed(input=self, value=event.text_area.text))

    # ── History navigation ────────────────────────────────────────────────────

    def _history_up(self) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._draft = self.value
        new_idx = min(self._history_index + 1, len(self._history) - 1)
        if new_idx == self._history_index:
            return
        self._history_index = new_idx
        self._load_and_end(self._history[self._history_index])

    def _history_down(self) -> None:
        if self._history_index == -1:
            return
        self._history_index -= 1
        text = self._draft if self._history_index == -1 else self._history[self._history_index]
        self._load_and_end(text)

    def _load_and_end(self, text: str) -> None:
        ta = self._textarea
        ta.load_text(text)
        lines = text.splitlines()
        if lines:
            ta.move_cursor((len(lines) - 1, len(lines[-1])))
        else:
            ta.move_cursor((0, 0))

