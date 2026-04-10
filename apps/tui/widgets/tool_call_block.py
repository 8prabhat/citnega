"""ToolCallBlock — shows an in-progress or completed tool invocation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Collapsible, Label, Static


class ToolCallBlock(Widget):
    """
    Collapsible card that shows a tool invocation result.

    ``set_result`` and ``set_error`` must be called from within the
    Textual event loop (from a message handler or async method).
    They are synchronous — no thread bridging needed.

    Args:
        tool_name:     Name of the tool (e.g. ``"search_files"``).
        input_summary: Short description of the tool input.
    """

    DEFAULT_CSS = """
    ToolCallBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        border-left: thick $secondary;
        background: $panel;
    }
    ToolCallBlock .tool-header {
        color: $secondary;
        text-style: bold;
        height: 1;
    }
    ToolCallBlock .tool-output {
        height: auto;
        color: $text-muted;
        margin-top: 0;
    }
    ToolCallBlock.error {
        border-left: thick $error;
    }
    ToolCallBlock.error .tool-header {
        color: $error;
    }
    ToolCallBlock Collapsible {
        height: auto;
        background: transparent;
        border: none;
        padding: 0;
    }
    """

    def __init__(
        self,
        tool_name: str,
        input_summary: str,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name     = tool_name
        self._input_summary = input_summary

    def compose(self) -> ComposeResult:
        yield Label(f"⚙ {self._tool_name}", classes="tool-header")
        with Collapsible(title=self._input_summary, collapsed=True):
            yield Static(
                "…running…",
                id="tool-output",
                classes="tool-output",
                markup=False,
            )

    def set_result(self, output: str) -> None:
        """Update the output area with a successful result (event-loop safe)."""
        try:
            self.query_one("#tool-output", Static).update(output)
        except Exception:
            pass

    def set_error(self, error: str) -> None:
        """Mark this block as failed and show the error (event-loop safe)."""
        try:
            self.add_class("error")
            self.query_one(".tool-header", Label).update(
                f"✗ {self._tool_name} (error)"
            )
            self.query_one("#tool-output", Static).update(f"Error: {error}")
        except Exception:
            pass
