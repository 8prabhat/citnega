"""ApprovalBlock — modern interactive card for approving or denying a tool execution."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ApprovalBlock(Widget):
    """
    Modern approval card — mounted in the chat scroll when a tool needs
    human confirmation before execution.

    Emits ``ApprovalBlock.Resolved`` which the app forwards to
    ``IApplicationService.respond_to_approval()``.
    """

    DEFAULT_CSS = """
    ApprovalBlock {
        margin: 1 0;
        padding: 1 2;
        border: tall $warning;
        background: $panel;
        height: auto;
    }
    ApprovalBlock .ap-badge {
        color: $warning;
        text-style: bold;
        height: 1;
    }
    ApprovalBlock .ap-tool {
        color: $text;
        text-style: bold;
        height: 1;
    }
    ApprovalBlock .ap-summary {
        color: $text-muted;
        height: auto;
        margin: 1 0;
    }
    ApprovalBlock #ap-divider {
        border-bottom: dashed $panel-lighten-2;
        height: 1;
        margin: 0 0 1 0;
    }
    ApprovalBlock #ap-buttons {
        layout: horizontal;
        height: 3;
    }
    ApprovalBlock #btn-approve {
        min-width: 12;
        margin-right: 2;
    }
    ApprovalBlock #btn-deny {
        min-width: 10;
    }
    ApprovalBlock.resolved {
        border: tall $panel-lighten-2;
        background: $surface;
        opacity: 0.7;
    }
    ApprovalBlock.resolved .ap-badge {
        color: $text-muted;
    }
    """

    class Resolved(Message):
        def __init__(self, approval_id: str, approved: bool) -> None:
            super().__init__()
            self.approval_id = approval_id
            self.approved = approved

    can_focus = True

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
        yield Label("⚠  Approval required  [y] approve  [n] deny  [Esc] dismiss", classes="ap-badge")
        yield Label(f"Tool: {self._callable_name}", classes="ap-tool")
        yield Static(self._input_summary, classes="ap-summary", markup=False)
        yield Widget(id="ap-divider")
        with Widget(id="ap-buttons"):
            yield Button("▶  Approve [y]", variant="success", id="btn-approve")
            yield Button("✗  Deny [n]", variant="error", id="btn-deny")

    def on_mount(self) -> None:
        self.focus()

    def on_key(self, event: Key) -> None:
        if self._resolved:
            return
        if event.key in ("y", "a"):
            event.stop()
            self._resolve(approved=True)
        elif event.key == "n":
            event.stop()
            self._resolve(approved=False)
        elif event.key == "escape":
            event.stop()
            self._resolve(approved=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._resolved:
            return
        self._resolve(approved=event.button.id == "btn-approve")

    def _resolve(self, *, approved: bool) -> None:
        self._resolved = True
        self._collapse(approved)
        self.post_message(self.Resolved(self._approval_id, approved))

    def _collapse(self, approved: bool) -> None:
        self.add_class("resolved")
        verb = "Approved" if approved else "Denied"
        icon = "✓" if approved else "✗"
        with contextlib.suppress(Exception):
            self.query_one(".ap-badge", Label).update(f"{icon}  {verb}: {self._callable_name}")
        for sel in (".ap-tool", ".ap-summary", "#ap-divider", "#ap-buttons"):
            with contextlib.suppress(Exception):
                self.query_one(sel).display = False
        with contextlib.suppress(Exception):
            self.blur()
