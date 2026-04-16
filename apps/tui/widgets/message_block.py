"""MessageBlock — renders a single completed user or assistant message."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Markdown, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

_ROLE_LABEL = {"user": "You", "assistant": "Citnega", "system": "System"}


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
        margin: 0 0 1 0;
        padding: 0 1 1 1;
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
    MessageBlock .role-label {
        text-style: bold;
        height: 1;
        margin-bottom: 0;
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

    def compose(self) -> ComposeResult:
        yield Label(_ROLE_LABEL.get(self._role, self._role), classes="role-label")
        if self._role == "assistant":
            yield Markdown(self._content, classes="content")
        else:
            yield Static(self._content, classes="content", markup=False)

    def on_click(self) -> None:
        """Clicking a message block focuses it so Ctrl+Y can copy it."""
        self.focus()
