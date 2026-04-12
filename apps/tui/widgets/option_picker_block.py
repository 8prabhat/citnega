"""
OptionPickerBlock — an inline, keyboard- and mouse-navigable option list.

Mounted into the chat scroll whenever a slash command wants the user to
select from a list (e.g. /model, /mode, /sessions).

Fires:
  OptionPickerBlock.Selected(value, label)  — user chose an option
  OptionPickerBlock.Dismissed               — user pressed Escape

The widget removes itself from the DOM after either event.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from textual.app import ComposeResult


class OptionPickerBlock(Widget):
    """
    Inline picker that wraps Textual's OptionList.

    Args:
        title:   Prompt shown above the list.
        options: ``[(value, display_label), ...]`` — value is what gets
                 reported in ``Selected``; label is what the user sees.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    OptionPickerBlock {
        height: auto;
        max-height: 18;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $primary;
        background: $surface;
    }
    OptionPickerBlock .picker-title {
        color: $text-muted;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    OptionPickerBlock .picker-hint {
        color: $text-muted;
        height: 1;
    }
    OptionPickerBlock OptionList {
        height: auto;
        max-height: 14;
        background: transparent;
    }
    """

    # ── Messages ──────────────────────────────────────────────────────────────

    class Selected(Message):
        """User selected an option."""

        def __init__(self, picker_id: str, value: str, label: str) -> None:
            super().__init__()
            self.picker_id = picker_id
            self.value = value
            self.label = label

    class Dismissed(Message):
        """User pressed Escape without selecting."""

        def __init__(self, picker_id: str) -> None:
            super().__init__()
            self.picker_id = picker_id

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._options = options  # [(value, display_label), ...]

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="picker-title")
        yield Label(
            "↑↓ navigate  ·  Enter / click to select  ·  Esc to cancel",
            classes="picker-hint",
        )
        items = [Option(label, id=value) for value, label in self._options]
        yield OptionList(*items)

    def on_mount(self) -> None:
        """Focus the list so arrow keys work immediately."""
        with contextlib.suppress(Exception):
            self.query_one(OptionList).focus()

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        value = str(event.option.id) if event.option.id is not None else str(event.option.prompt)
        label = str(event.option.prompt)
        self.post_message(self.Selected(picker_id=self.id or "", value=value, label=label))
        # Remove self after selection so the chat keeps its clean history look
        self.remove()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_dismiss(self) -> None:
        self.post_message(self.Dismissed(picker_id=self.id or ""))
        self.remove()
