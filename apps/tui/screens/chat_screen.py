"""
ChatScreen — the main (and only) screen of the Citnega TUI.

Layout::

    ┌──────────────────────────────────────────────────┐
    │  VerticalScroll (id="chat-scroll")               │
    │    MessageBlock / StreamingBlock / ToolCallBlock │
    │    ApprovalBlock                                 │
    │                                              … │
    ├──────────────────────────────────────────────────┤
    │  Input (id="chat-input")                         │
    ├──────────────────────────────────────────────────┤
    │  StatusBar                                       │
    └──────────────────────────────────────────────────┘

The screen does NOT import ApplicationService directly — it communicates
with the outside world only through Textual messages posted by
EventConsumerWorker and handled by the ChatController mixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label

from citnega.apps.tui.widgets.status_bar import StatusBar

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChatScreen(Screen):
    """Single-pane conversational screen."""

    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+y", "copy_last", "Copy", show=True),
        Binding("escape", "dismiss_popup", "Dismiss", show=False),
        Binding("tab", "focus_input", "Input", show=False),
        Binding("ctrl+k", "toggle_slash_popup", "Slash", show=False),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
    }
    #chat-scroll {
        height: 1fr;
        border-bottom: solid $panel-lighten-1;
        scrollbar-size: 1 1;
    }
    #chat-input {
        height: 3;
        dock: bottom;
        border: solid $accent;
    }
    #chat-input:focus {
        border: solid $success;
    }
    #empty-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 4;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Label(
                "Type a message below. Use /help to see available commands.",
                id="empty-hint",
            ),
            id="chat-scroll",
        )
        yield Input(placeholder="Ask anything… (/ for commands)", id="chat-input")
        yield StatusBar()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.query_one("#chat-input", Input).focus()

    # ── Input submission ───────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        # Delegate to the App which owns the ChatController
        self.app.post_message(UserInputSubmitted(text=text))

    # ── Action handlers ────────────────────────────────────────────────────────

    def action_clear_chat(self) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.remove_children()
        # Restore empty hint
        scroll.mount(
            Label(
                "Chat cleared. Type a message below.",
                id="empty-hint",
            )
        )

    def action_copy_last(self) -> None:
        """Copy the last assistant message to the system clipboard (cross-platform)."""
        from citnega.apps.tui.widgets.message_block import MessageBlock
        from citnega.apps.tui.widgets.streaming_block import StreamingBlock

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        for block in reversed(list(scroll.children)):
            text: str | None = None
            if isinstance(block, MessageBlock) and block._role == "assistant":
                text = block._content
            elif isinstance(block, StreamingBlock) and block.text:
                text = block.text
            if text:
                try:
                    _copy_to_clipboard(text)
                    self.app.notify("Copied to clipboard.", timeout=2)
                except Exception as exc:
                    self.app.notify(f"Copy failed: {exc}", severity="error", timeout=3)
                return
        self.app.notify("No assistant message to copy.", timeout=2)

    def action_focus_input(self) -> None:
        self.query_one("#chat-input", Input).focus()

    def action_dismiss_popup(self) -> None:
        # Handled by App if a popup is mounted
        self.app.post_message(DismissPopup())

    def action_toggle_slash_popup(self) -> None:
        self.app.post_message(ToggleSlashPopup())


# ── Screen-level messages (consumed by CItnega App) ───────────────────────────


def _copy_to_clipboard(text: str) -> None:
    """Copy text to clipboard — works on macOS, Linux (xclip/xsel/wl-copy), Windows."""
    import subprocess
    import sys

    encoded = text.encode("utf-8")
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=encoded, check=True)
    elif sys.platform.startswith("linux"):
        for cmd in [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["wl-copy"],
        ]:
            try:
                subprocess.run(cmd, input=encoded, check=True)
                return
            except FileNotFoundError:
                continue
        raise RuntimeError("No clipboard tool found — install xclip, xsel, or wl-copy")
    else:  # Windows
        subprocess.run(["clip"], input=encoded, check=False)


from textual.message import Message as _Msg  # noqa: E402


class UserInputSubmitted(_Msg):
    """User submitted a line of text from the chat input."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class DismissPopup(_Msg):
    """Request to dismiss any overlay popup."""


class ToggleSlashPopup(_Msg):
    """Toggle the slash-command suggestion popup."""
