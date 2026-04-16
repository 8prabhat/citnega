"""SlashCommandPopup — overlay widget showing slash command suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from textual.app import ComposeResult


class SlashCommandPopup(Widget):
    """
    A floating popup listing available slash commands.

    Dismissed by Escape or clicking outside.
    Selecting an item inserts the command into the chat input.
    """

    DEFAULT_CSS = """
    SlashCommandPopup {
        layer: overlay;
        dock: bottom;
        height: auto;
        max-height: 12;
        width: 40;
        margin-bottom: 4;
        margin-left: 1;
        border: solid $accent;
        background: $surface;
    }
    SlashCommandPopup #popup-list {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
    ]

    def __init__(self, commands: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._commands = commands

    def compose(self) -> ComposeResult:
        items = [ListItem(Label(f"/{cmd}"), id=f"slash-{cmd}") for cmd in self._commands]
        yield ListView(*items, id="popup-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """User selected a command — insert it into the chat input."""
        from textual.widgets import Input

        cmd_label = event.item.query_one(Label).renderable
        cmd_text = str(cmd_label)

        try:
            inp = self.app.query_one("#chat-input", Input)
            inp.value = cmd_text + " "
            inp.cursor_position = len(inp.value)
            inp.focus()
        except Exception:
            pass

        self.remove()
        try:
            controller = getattr(self.app, "_controller", None)
            if controller is not None:
                controller._popup = None
        except Exception:
            pass

    def action_dismiss(self) -> None:
        try:
            controller = getattr(self.app, "_controller", None)
            if controller is not None:
                controller.dismiss_popup()
        except Exception:
            self.remove()
