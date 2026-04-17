"""MessageBlock — renders a single completed user or assistant message."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Markdown, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

# Short role badge shown inline at the top of each block
_ROLE_BADGE = {"user": "▸ you", "assistant": "◈ citnega", "system": "⊘ system"}


class MessageBlock(Widget):
    """
    An immutable message bubble.

    Args:
        role:    ``"user"`` | ``"assistant"`` | ``"system"``
        content: Full text of the message.

    Click to focus; Ctrl+Y copies the focused block's content.
    """

    can_focus = True

    DEFAULT_CSS = """
    MessageBlock {
        height: auto;
        margin: 0 0 0 0;
        padding: 0 1 1 1;
        border-top: solid $panel-lighten-1;
    }

    /* ── User bubble ──────────────────────────────────────── */
    MessageBlock.user {
        border-left: thick $accent;
        background: $boost;
    }
    MessageBlock.user .role-label {
        color: $accent;
    }

    /* ── Assistant bubble ─────────────────────────────────── */
    MessageBlock.assistant {
        border-left: thick $success;
        background: $surface;
    }
    MessageBlock.assistant .role-label {
        color: $success;
    }

    /* ── System / info bubble ─────────────────────────────── */
    MessageBlock.system {
        border-left: thick $panel-lighten-3;
        background: $surface;
    }
    MessageBlock.system .role-label {
        color: $text-disabled;
    }
    MessageBlock.system .content {
        color: $text-muted;
        text-style: italic;
    }

    /* ── Focus highlight (click-to-select) ────────────────── */
    MessageBlock:focus {
        border: dashed $accent-darken-1;
        background: $boost;
        outline: none;
    }

    /* ── Shared label / content ───────────────────────────── */
    MessageBlock .role-header {
        layout: horizontal;
        height: 1;
        margin-bottom: 0;
    }
    MessageBlock .role-label {
        text-style: bold;
        width: 1fr;
    }
    MessageBlock .timestamp {
        color: $text-disabled;
        text-style: dim;
        content-align: right middle;
    }
    MessageBlock .content {
        height: auto;
        margin: 0;
        padding: 0;
    }
    MessageBlock Markdown {
        height: auto;
        margin: 0;
        padding: 0;
        background: transparent;
    }
    """

    def __init__(self, role: str, content: str, **kwargs) -> None:
        super().__init__(classes=role, **kwargs)
        self._role = role
        self._content = content
        self._timestamp = datetime.now().strftime("%H:%M")

    def compose(self) -> ComposeResult:
        badge = _ROLE_BADGE.get(self._role, self._role)
        with Widget(classes="role-header"):
            yield Label(badge, classes="role-label")
            yield Label(self._timestamp, classes="timestamp")
        if self._role == "assistant":
            yield Markdown(self._content, classes="content")
        else:
            yield Static(self._content, classes="content", markup=False)

    def on_click(self) -> None:
        """Clicking a message block focuses it so Ctrl+Y can copy it."""
        self.focus()
