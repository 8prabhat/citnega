"""MessageBlock — renders a single completed user or assistant message."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Markdown, Static


class MessageBlock(Widget):
    """
    An immutable message bubble.

    Args:
        role:    "user" | "assistant" | "system"
        content: Full text of the message.

    Assistant messages are rendered as Markdown (code blocks, bold, etc.).
    User and system messages are rendered as plain text.
    """

    DEFAULT_CSS = """
    MessageBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    MessageBlock.user {
        border-left: thick $accent;
        background: $boost;
    }
    MessageBlock.assistant {
        border-left: thick $success;
        background: $surface;
    }
    MessageBlock.system {
        border-left: thick $warning;
        background: $surface;
        color: $text-muted;
    }
    MessageBlock .role-label {
        color: $text-muted;
        text-style: bold;
        height: 1;
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
        self._role    = role
        self._content = content

    def compose(self) -> ComposeResult:
        _ROLE_LABELS = {"user": "You", "assistant": "Citnega", "system": "System"}
        yield Label(_ROLE_LABELS.get(self._role, self._role), classes="role-label")
        if self._role == "assistant":
            yield Markdown(self._content, classes="content")
        else:
            yield Static(self._content, classes="content", markup=False)
