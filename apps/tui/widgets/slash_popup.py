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
    A floating popup listing available slash commands with descriptions.

    Dismissed by Escape or clicking outside.
    Selecting an item inserts the command into the chat input.
    """

    DEFAULT_CSS = """
    SlashCommandPopup {
        layer: overlay;
        dock: bottom;
        height: auto;
        max-height: 14;
        width: 58;
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

    def __init__(self, commands: list[tuple[str, str]], **kwargs) -> None:
        """
        Args:
            commands: List of ``(name, description)`` tuples.
        """
        super().__init__(**kwargs)
        self._commands = commands

    def compose(self) -> ComposeResult:
        items = []
        for name, desc in self._commands:
            # Build a single line: "/name  — short description"
            desc_short = desc[:36] if desc else ""
            line = f"/{name:<12}  {desc_short}" if desc_short else f"/{name}"
            items.append(ListItem(Label(line), id=f"slash-{name}"))
        yield ListView(*items, id="popup-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """User selected a command — insert it into the chat input."""
        from textual.widgets import Input

        item_id = event.item.id or ""
        cmd_name = item_id.removeprefix("slash-")
        cmd_text = f"/{cmd_name}"

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
