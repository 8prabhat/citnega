"""PlanApprovalBlock — inline widget asking the user to approve or cancel a plan."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label

if TYPE_CHECKING:
    from textual.app import ComposeResult


class PlanApprovalBlock(Widget):
    """
    Shown after plan-mode generates a draft plan.

    Presents two buttons — "Proceed" and "Cancel" — and posts a
    ``PlanApprovalBlock.Resolved`` message to the app when the user
    makes a choice.

    The widget removes itself from the DOM once resolved so the chat
    area stays clean.
    """

    class Resolved(Message):
        """Posted when the user clicks Proceed or Cancel."""

        def __init__(self, approved: bool) -> None:
            super().__init__()
            self.approved = approved

    DEFAULT_CSS = """
    PlanApprovalBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 1 2;
        border-left: thick $warning;
        background: $panel;
        layout: vertical;
    }
    PlanApprovalBlock .approval-label {
        color: $warning;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    PlanApprovalBlock .button-row {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    PlanApprovalBlock Button {
        margin-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(
            "▶ Plan ready — proceed with execution?",
            classes="approval-label",
        )
        with Widget(classes="button-row"):
            yield Button("▶ Proceed", id="btn-proceed", variant="success")
            yield Button("✗ Cancel", id="btn-cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        approved = event.button.id == "btn-proceed"
        self.post_message(self.Resolved(approved=approved))
        # Remove self so the chat area is not cluttered after resolution
        self.remove()
