"""
ChatScreen — the main (and only) screen of the Citnega TUI.

Layout::

    ┌──────────────────────────────────────────────────────┐
    │  #chat-scroll  (full width, 1fr)                     │
    │  MessageBlock (user / assistant / system)            │
    │  ThinkingBlock  (collapsible, inline)                │
    │  ToolCallBlock  (inline — click to expand)           │
    │  AgentCallBlock (inline — click to expand)           │
    │  StreamingBlock (live response)                      │
    │  ApprovalBlock / PlanApprovalBlock                   │
    ╞══════════════════════════════════════════════════════╡  ← thick divider (on SmartInput top)
    │  SmartInput  (multi-line, ↑↓ history, /)            │
    ├──────────────────────────────────────────────────────┤
    │  ContextBar line 1: session│◈model│mode│folder│tok  │  ← live session state
    │  ContextBar line 2: ⚙ rounds│depth│local│policy│…   │  ← static config (no overlap)
    └──────────────────────────────────────────────────────┘

ContextBar owns both lines — zero duplicate information.

Tool and agent calls are rendered inline in the chat stream (Claude Code style),
not in a separate sidebar.  Click any completed call to expand input + output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen

from citnega.apps.tui.widgets.context_bar import ContextBar
from citnega.apps.tui.widgets.smart_input import SmartInput
from citnega.apps.tui.widgets.welcome_banner import WelcomeBanner

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChatScreen(Screen):
    """Full-width conversational screen with inline tool/agent call blocks."""

    BINDINGS = [
        Binding("ctrl+c", "app.quit",            "Quit",     show=True),
        Binding("f2",     "settings",             "Settings", show=True),
        Binding("f3",     "history",              "History",  show=True),
        Binding("ctrl+l", "clear_chat",           "Clear",    show=True),
        Binding("ctrl+y", "copy_last",            "Copy",     show=True),
        Binding("escape", "dismiss_popup",        "Dismiss",  show=False),
        Binding("tab",    "focus_input",          "Input",    show=False),
        Binding("ctrl+k", "toggle_slash_popup",   "Commands", show=False),
        # Priority binding — fires before TextArea sees the key, so it intercepts
        # even when TextArea is focused.  ctrl+enter is not reliably distinguishable
        # from plain Enter on standard terminals, so we use ctrl+s as the submit key.
        Binding("ctrl+s", "submit_input",         "Send",     show=False, priority=True),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
        background: $background;
    }

    /* ── CHAT AREA ─────────────────────────────────────────── */
    #chat-scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-color: $panel-lighten-2 transparent;
        padding: 0 2 1 2;
        background: $background;
    }

    /* ── Input — full-height multiline prompt panel ─────────── */
    #chat-input {
        height: auto;
        min-height: 7;
        max-height: 14;
    }

    /* ── ContextBar — 2-line strip: state + config ─────────── */
    #context-bar {
        height: 2;
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
        with VerticalScroll(id="chat-scroll"):
            yield WelcomeBanner(id="empty-hint")
        yield SmartInput(id="chat-input")
        yield ContextBar(id="context-bar")

    def on_mount(self) -> None:
        self.query_one("#chat-input", SmartInput).focus()

    def on_smart_input_submitted(self, event: SmartInput.Submitted) -> None:
        smart = event.input
        if not isinstance(smart, SmartInput):
            return
        text = smart.submit_and_clear()
        if not text:
            return
        self.app.post_message(UserInputSubmitted(text=text))

    def on_smart_input_changed(self, event: SmartInput.Changed) -> None:
        """Forward input changes to the controller for slash-popup live filter."""
        try:
            ctrl = getattr(self.app, "_controller", None)
            if ctrl is not None:
                ctrl.on_input_value_changed(event.value)
        except Exception:
            pass

    def action_clear_chat(self) -> None:
        # remove_children() schedules removal asynchronously; defer placeholder
        # remount to after the next refresh so removals have settled.
        self.query_one("#chat-scroll", VerticalScroll).remove_children()
        self.call_after_refresh(self._remount_placeholders)

    def _remount_placeholders(self) -> None:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        if not scroll.query("#empty-hint"):
            scroll.mount(WelcomeBanner(id="empty-hint"))

    def action_copy_last(self) -> None:
        from citnega.apps.tui.widgets.message_block import MessageBlock
        from citnega.apps.tui.widgets.streaming_block import StreamingBlock

        # ── Tier 1: SmartInput TextArea has an active text selection ─────────
        try:
            smart = self.query_one("#chat-input", SmartInput)
            if smart.is_input_focused:
                sel = smart.selected_text
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

    def action_submit_input(self) -> None:
        """Priority Ctrl+S — submit the current SmartInput content."""
        from textual.actions import SkipAction
        ctrl = getattr(self.app, "_controller", None)
        if ctrl is not None and getattr(ctrl, "_slash_screen_open", False):
            raise SkipAction()
        smart = self.query_one("#chat-input", SmartInput)
        smart.post_message(SmartInput.Submitted(input=smart))

    def action_focus_input(self) -> None:
        self.query_one("#chat-input", SmartInput).focus()

    def action_dismiss_popup(self) -> None:
        self.app.post_message(DismissPopup())

    def action_toggle_slash_popup(self) -> None:
        self.app.post_message(ToggleSlashPopup())

    def action_settings(self) -> None:
        from citnega.apps.tui.screens.settings_screen import SettingsScreen

        service = getattr(self.app, "service", None)
        self.app.push_screen(SettingsScreen(service=service), self._on_settings_closed)

    def action_history(self) -> None:
        from citnega.apps.tui.screens.history_screen import HistoryScreen

        service = getattr(self.app, "service", None)
        self.app.push_screen(HistoryScreen(service=service))

    def _on_settings_closed(self, saved: bool | None = None) -> None:
        """Refresh the ContextBar config line after the settings screen closes."""
        import contextlib
        with contextlib.suppress(Exception):
            self.query_one("#context-bar", ContextBar).refresh_config()


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
