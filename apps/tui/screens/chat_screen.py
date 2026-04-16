"""
ChatScreen — the main (and only) screen of the Citnega TUI.

Layout::

    ┌───────────────────────────────┬──────────────────────┐
    │  #chat-scroll  (3fr)          │  #tools-panel (1fr)  │
    │  MessageBlock                 │  ─── Tools ───       │
    │  StreamingBlock               │  ToolCallBlock       │
    │  ThinkingBlock                │  ToolCallBlock       │
    │  ApprovalBlock                │  …                   │
    ├───────────────────────────────┴──────────────────────┤
    │  SmartInput  (multi-line paste + history)            │
    ├──────────────────────────────────────────────────────┤
    │  StatusBar                                           │
    └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Label

from citnega.apps.tui.widgets.context_bar import ContextBar
from citnega.apps.tui.widgets.smart_input import SmartInput
from citnega.apps.tui.widgets.status_bar import StatusBar
from citnega.apps.tui.widgets.welcome_banner import WelcomeBanner

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChatScreen(Screen):
    """Two-panel conversational screen: chat left, tools right."""

    BINDINGS = [
        Binding("ctrl+c", "app.quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+y", "copy_last", "Copy", show=True),
        Binding("escape", "dismiss_popup", "Dismiss", show=False),
        Binding("tab", "focus_input", "Input", show=False),
        Binding("ctrl+k", "toggle_slash_popup", "Commands", show=False),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
        background: $background;
    }

    #main-area {
        layout: horizontal;
        height: 1fr;
    }

    /* ── Chat scroll (left, wider) ─────────────────────────── */
    #chat-scroll {
        width: 3fr;
        border-right: solid $panel-lighten-2;
        scrollbar-size: 1 1;
        scrollbar-color: $panel-lighten-2 transparent;
        padding: 0 1 1 1;
    }

    /* ── Tools sidebar (right) ─────────────────────────────── */
    #tools-panel-wrapper {
        width: 1fr;
        layout: vertical;
        background: $surface;
    }
    #tools-panel-header {
        height: 1;
        background: $panel;
        color: $secondary;
        padding: 0 1;
        text-style: bold;
        border-bottom: solid $panel-lighten-2;
    }
    #tools-panel {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-color: $panel-lighten-2 transparent;
        padding: 0 1 1 1;
    }
    #tools-empty {
        color: $text-disabled;
        margin: 2 0;
        text-align: center;
        text-style: italic;
    }

    /* ── Context bar (above input) ─────────────────────────── */
    /* height:1 is set inside the widget's own DEFAULT_CSS;    */
    /* background: $panel-darken-1 provides visual separation. */

    /* ── Smart input ───────────────────────────────────────── */
    #chat-input {
        height: 3;
        border-top: solid $panel-lighten-2;
        border-left: none;
        border-right: none;
        border-bottom: none;
        background: $surface;
        padding: 0 2;
    }
    #chat-input:focus {
        border-top: solid $accent;
        background: $boost;
    }

    #empty-hint {
        color: $text-disabled;
        text-align: center;
        margin-top: 5;
        height: auto;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-area"):
            with VerticalScroll(id="chat-scroll"):
                yield WelcomeBanner(id="empty-hint")
            with Widget(id="tools-panel-wrapper"):
                yield Label("⚙  Tools", id="tools-panel-header")
                with VerticalScroll(id="tools-panel"):
                    yield Label("No active tools", id="tools-empty")
        yield ContextBar(id="context-bar")
        yield SmartInput(
            placeholder="Ask anything…   ↑↓ history   / for commands",
            id="chat-input",
        )
        yield StatusBar()

    def on_mount(self) -> None:
        self.query_one("#chat-input", SmartInput).focus()

    def on_input_submitted(self, event: SmartInput.Submitted) -> None:
        smart = event.input
        if not isinstance(smart, SmartInput):
            return
        text = smart.submit_and_clear()
        if not text:
            return
        self.app.post_message(UserInputSubmitted(text=text))

    def action_clear_chat(self) -> None:
        # remove_children() schedules removal asynchronously; if we mount
        # immediately in the same tick the old nodes are still registered and
        # Textual raises DuplicateIds.  Defer all placeholder mounts to after
        # the next refresh so the removals are guaranteed to have settled.
        self.query_one("#chat-scroll", VerticalScroll).remove_children()
        self.query_one("#tools-panel", VerticalScroll).remove_children()
        self.call_after_refresh(self._remount_placeholders)

    def _remount_placeholders(self) -> None:
        """Mount the empty-state placeholders only if they don't already exist."""
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        if not scroll.query("#empty-hint"):
            scroll.mount(WelcomeBanner(id="empty-hint"))
        tools = self.query_one("#tools-panel", VerticalScroll)
        if not tools.query("#tools-empty"):
            tools.mount(Label("No active tools", id="tools-empty"))

    def action_copy_last(self) -> None:
        from citnega.apps.tui.widgets.message_block import MessageBlock
        from citnega.apps.tui.widgets.streaming_block import StreamingBlock

        # ── Tier 1: SmartInput has an active text selection ───────────────────
        # Only applies when the cursor is actually inside the input widget and
        # text is selected within it — the one place where sub-character
        # selection is meaningful in Textual.
        try:
            smart = self.query_one("#chat-input", SmartInput)
            if self.app.focused is smart:
                selection = smart.selection  # Selection(start, end) — int column pos
                start, end = selection.start, selection.end
                if start != end:
                    lo, hi = min(start, end), max(start, end)
                    sel = smart.value[lo:hi]
                    if sel:
                        _copy_to_clipboard(sel)
                        self.app.notify("Copied selection.", timeout=2)
                        return
        except Exception:
            pass

        # ── Tier 2: A message block is focused (user clicked it) ──────────────
        # MessageBlock and StreamingBlock are focusable. Clicking one focuses it
        # and shows a dashed border. Ctrl+Y then copies that block's full text.
        focused = self.app.focused
        try:
            if isinstance(focused, MessageBlock):
                _copy_to_clipboard(focused._content)
                self.app.notify("Copied message. (click any message to select it)", timeout=2)
                return
            if isinstance(focused, StreamingBlock) and focused.text:
                _copy_to_clipboard(focused.text)
                self.app.notify("Copied response.", timeout=2)
                return
        except Exception as exc:
            self.app.notify(f"Copy failed: {exc}", severity="error", timeout=3)
            return

        # ── Tier 3: Fallback — copy the last assistant message ────────────────
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
                    self.app.notify(
                        "Copied last response. (click a message first to copy a specific one)",
                        timeout=3,
                    )
                except Exception as exc:
                    self.app.notify(f"Copy failed: {exc}", severity="error", timeout=3)
                return
        self.app.notify("Nothing to copy.", timeout=2)

    def action_focus_input(self) -> None:
        self.query_one("#chat-input", SmartInput).focus()

    def action_dismiss_popup(self) -> None:
        self.app.post_message(DismissPopup())

    def action_toggle_slash_popup(self) -> None:
        self.app.post_message(ToggleSlashPopup())


# ── Clipboard ─────────────────────────────────────────────────────────────────


def _copy_to_clipboard(text: str) -> None:
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
    else:
        subprocess.run(["clip"], input=encoded, check=False)


# ── Messages ──────────────────────────────────────────────────────────────────

from textual.message import Message as _Msg  # noqa: E402


class UserInputSubmitted(_Msg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class DismissPopup(_Msg):
    pass


class ToggleSlashPopup(_Msg):
    pass
