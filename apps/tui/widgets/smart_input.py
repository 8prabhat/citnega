"""
SmartInput — multi-line paste support + command history for the chat input.

Features
--------
- **Multi-line paste**: When the user pastes text containing newlines the
  display inserts ``[[PASTED N LINES]]`` at the cursor position so the user
  can still type context around it, e.g.:
      "Could you review: [[PASTED 42 LINES]]"
  On submit the tag is replaced with the actual pasted content.
- **Command history**: Up / Down arrow keys navigate previously submitted
  commands (like a shell).  The current draft is saved and restored when
  the user arrows back to the bottom.
- **Normal single-line text**: Behaves exactly like the standard ``Input``
  widget when no multi-line paste is in progress.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from textual.events import Key, Paste
from textual.widgets import Input

if TYPE_CHECKING:
    pass

_MAX_HISTORY_DEFAULT = 200


def _get_max_history() -> int:
    try:
        from citnega.packages.config.loaders import load_settings

        return load_settings().tui.input_history_size
    except Exception:
        return _MAX_HISTORY_DEFAULT


class SmartInput(Input):
    """
    Single-line ``Input`` subclass with:

    * Multi-line paste collapsed to ``[[PASTED N LINES]]`` (inserted at cursor)
    * User can type context before/after the tag
    * Command history navigated with ↑ / ↓
    """

    def __init__(self, **kwargs) -> None:
        # Disable auto-select-all on re-focus so the user's typed text is never
        # silently replaced when they click away and come back.
        kwargs.setdefault("select_on_focus", False)
        super().__init__(**kwargs)
        # Full pasted text stored when a multi-line paste tag is present
        self._pasted_text: str = ""
        self._history: deque[str] = deque(maxlen=_get_max_history())
        self._history_index: int = -1   # -1 = not browsing
        self._draft: str = ""           # unsaved draft when browsing history

    # ── Tag helpers ───────────────────────────────────────────────────────────

    def _paste_tag(self) -> str:
        if not self._pasted_text:
            return ""
        return f"[[PASTED {len(self._pasted_text.splitlines())} LINES]]"

    # ── Actual value (real content behind the summary label) ─────────────────

    @property
    def actual_value(self) -> str:
        """
        The text that will be submitted.

        Replaces the ``[[PASTED N LINES]]`` tag in the current input value
        with the real pasted content, so users can write context around it:
            "Could you review: [[PASTED 42 LINES]]"  →
            "Could you review: <actual 42-line block>"
        """
        if not self._pasted_text:
            return self.value
        return self.value.replace(self._paste_tag(), self._pasted_text, 1)

    def seed_history(self, messages: list[str]) -> None:
        """
        Populate arrow-key history from a list of past messages.

        Pass messages oldest-first; the newest will end up at index 0
        (first result when pressing Up).  Clears any existing history.
        """
        self._history.clear()
        self._history_index = -1
        self._draft = ""
        for msg in messages:
            if msg:
                self._history.appendleft(msg)

    def submit_and_clear(self) -> str:
        """Consume the current value, add to history, clear the input."""
        text = self.actual_value.strip()
        if text:
            self._history.appendleft(text)
        self._history_index = -1
        self._draft = ""
        self._pasted_text = ""
        self.value = ""
        return text

    # ── Paste interception ────────────────────────────────────────────────────

    def _on_paste(self, event: Paste) -> None:
        """Insert multi-line paste as a summary tag.

        Replaces the current selection (if any) with the tag so that pasting
        while text is selected behaves the same as a normal paste.  When there
        is no selection the tag is inserted at the cursor position, preserving
        all surrounding text.
        """
        text = event.text
        lines = text.splitlines()
        if len(lines) <= 1:
            # Single-line: let Textual handle it normally; clear paste state
            # so a stale _pasted_text doesn't shadow the newly inserted text.
            self._pasted_text = ""
            return

        self._pasted_text = text
        tag = self._paste_tag()

        # sorted() normalises both "cursor at start" and "cursor at end"
        # selections so start ≤ end regardless of selection direction.
        start, end = sorted(self.selection)
        current = self.value
        self.value = current[:start] + tag + current[end:]
        self.cursor_position = start + len(tag)

        event.prevent_default()
        event.stop()

    # ── History navigation via ↑ / ↓ ─────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        if event.key == "up":
            self._history_up()
            event.prevent_default()
            event.stop()
        elif event.key == "down":
            self._history_down()
            event.prevent_default()
            event.stop()

    def _history_up(self) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._draft = self.actual_value
        new_idx = min(self._history_index + 1, len(self._history) - 1)
        if new_idx == self._history_index:
            return
        self._history_index = new_idx
        self._pasted_text = ""
        self.value = self._history[self._history_index]
        self.cursor_position = len(self.value)

    def _history_down(self) -> None:
        if self._history_index == -1:
            return
        self._history_index -= 1
        self._pasted_text = ""
        if self._history_index == -1:
            self.value = self._draft
        else:
            self.value = self._history[self._history_index]
        self.cursor_position = len(self.value)

    # ── Guard: clear paste state only on explicit submit or new session ──────────
    # NOTE: We intentionally do NOT clear _pasted_text in on_input_changed.
    # actual_value.replace(tag, content) is a no-op when the tag is absent,
    # so correctness is preserved even if the user partially deletes the tag.
    # Clearing eagerly here was causing bug 2: any accidental Backspace into the
    # tag would silently lose the pasted content before submit.
