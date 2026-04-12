"""
CodingBlock — TUI widget showing live code-generation progress.

Mounted in the chat scroll when the user runs /createtool, /createagent,
or /createworkflow.  Displays:

  ┌─ Coding: web_scraper_tool ─────────────────────────────────────────┐
  │  ● Generating code (attempt 1/3)…                                  │
  │                                                                     │
  │  <streamed LLM tokens appear here as they arrive>                  │
  │                                                                     │
  │  ✔ Tests passed in 42 ms.                                          │
  │  ✔ Registered as 'web_scraper_tool'                                │
  └────────────────────────────────────────────────────────────────────┘

The widget is finalised (made static) once generation completes or fails.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class CodingBlock(Widget):
    """
    Live coding-progress block.

    Args:
        title:     Header title, e.g. "web_scraper_tool".
        kind:      "tool" | "agent" | "workflow".
    """

    DEFAULT_CSS = """
    CodingBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1 1 1;
        border-left: thick $warning;
        background: $surface;
    }
    CodingBlock .cb-header {
        color: $warning;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    CodingBlock .cb-status {
        color: $text-muted;
        height: 1;
    }
    CodingBlock .cb-code {
        color: $text;
        background: $panel;
        padding: 0 1;
        margin: 1 0;
    }
    CodingBlock .cb-result-pass {
        color: $success;
        height: auto;
    }
    CodingBlock .cb-result-fail {
        color: $error;
        height: auto;
    }
    """

    def __init__(self, title: str, kind: str = "tool", **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._kind = kind
        self._tokens: list[str] = []

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        kind_icon = {"tool": "🔧", "agent": "🤖", "workflow": "⚙️"}.get(self._kind, "◆")
        yield Label(
            f"{kind_icon} Coding: {self._title}",
            classes="cb-header",
        )
        yield Label("Initialising…", id="cb-status", classes="cb-status")
        yield Static("", id="cb-code", classes="cb-code")
        yield Static("", id="cb-result", classes="cb-result-pass")

    # ── Public update API (called from workspace.py) ──────────────────────────

    def set_status(self, text: str) -> None:
        """Update the one-line status message (step indicator)."""
        with contextlib.suppress(Exception):
            self.query_one("#cb-status", Label).update(text)

    def append_token(self, token: str) -> None:
        """Append a code token from the streaming LLM output."""
        self._tokens.append(token)
        code_so_far = "".join(self._tokens)
        # Only show last 40 lines to keep height reasonable
        lines = code_so_far.splitlines()[-40:]
        with contextlib.suppress(Exception):
            self.query_one("#cb-code", Static).update("\n".join(lines))

    def set_result_pass(self, message: str) -> None:
        """Show a green success result and collapse the code block."""
        try:
            self.query_one("#cb-status", Label).update("")
            self.query_one("#cb-code", Static).update("")  # hide code detail
            w = self.query_one("#cb-result", Static)
            w.remove_class("cb-result-fail")
            w.add_class("cb-result-pass")
            w.update(f"✔ {message}")
        except Exception:
            pass

    def set_result_fail(self, message: str) -> None:
        """Show a red failure result."""
        try:
            self.query_one("#cb-status", Label).update("")
            w = self.query_one("#cb-result", Static)
            w.remove_class("cb-result-pass")
            w.add_class("cb-result-fail")
            w.update(f"✘ {message}")
        except Exception:
            pass

    def clear_code(self) -> None:
        """Clear accumulated tokens between retry attempts."""
        self._tokens.clear()
        with contextlib.suppress(Exception):
            self.query_one("#cb-code", Static).update("")
