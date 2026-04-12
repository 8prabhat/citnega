"""ApprovalBlock — interactive card for approving or denying a tool execution."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ApprovalBlock(Widget):
    """
    Interactive approval card.

    Rendered when ApprovalRequestEvent arrives.  The user clicks
    "Approve" or "Deny" to resolve the approval.

    Emits ApprovalBlock.Resolved message which the App forwards to
    IApplicationService.respond_to_approval().
    """

    DEFAULT_CSS = """
    ApprovalBlock {
        margin: 0 0 1 0;
        padding: 1 1;
        border: solid $warning;
        background: $panel;
        height: auto;
    }
    ApprovalBlock .approval-header {
        color: $warning;
        text-style: bold;
        height: 1;
    }
    ApprovalBlock .approval-summary {
        margin: 1 0;
        color: $text;
    }
    ApprovalBlock #approval-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 1;
    }
    ApprovalBlock #btn-approve {
        margin-right: 2;
    }
    ApprovalBlock.resolved {
        border: solid $panel-lighten-1;
        opacity: 0.5;
    }
    ApprovalBlock.resolved .approval-header {
        color: $text-muted;
    }
    """

    class Resolved(Message):
        """Emitted when the user clicks Approve or Deny."""

        def __init__(self, approval_id: str, approved: bool) -> None:
            super().__init__()
            self.approval_id = approval_id
            self.approved = approved

    def __init__(
        self,
        approval_id: str,
        callable_name: str,
        input_summary: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._approval_id = approval_id
        self._callable_name = callable_name
        self._input_summary = input_summary
        self._resolved = False

    def compose(self) -> ComposeResult:
        yield Label(f"⚠ Approval required: {self._callable_name}", classes="approval-header")
        yield Static(self._input_summary, classes="approval-summary", markup=False)
        with Widget(id="approval-buttons"):
            yield Button("Approve", variant="success", id="btn-approve")
            yield Button("Deny", variant="error", id="btn-deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._resolved:
            return
        self._resolved = True
        approved = event.button.id == "btn-approve"
        self._mark_resolved(approved)
        self.post_message(self.Resolved(self._approval_id, approved))

    def _mark_resolved(self, approved: bool) -> None:
        self.add_class("resolved")
        header = self.query_one(".approval-header", Label)
        verb = "Approved" if approved else "Denied"
        header.update(f"{'✓' if approved else '✗'} {verb}: {self._callable_name}")
        # Hide buttons
        with contextlib.suppress(Exception):
            self.query_one("#approval-buttons").display = False
