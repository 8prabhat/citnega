"""ToolCallBlock — inline Claude Code-style tool call, mounted in the chat stream."""

from __future__ import annotations

import contextlib
import json
import time
from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Click
    from textual.timer import Timer

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_ICON_OK  = "✓"
_ICON_ERR = "✗"
_BULLET   = "◆"


def _elapsed_str(seconds: float) -> str:
    if seconds < 1.0:
        return f"[{int(seconds * 1000)}ms]"
    return f"[{seconds:.1f}s]"


def _args_inline(raw: str, max_len: int = 55) -> str:
    """Compact single-line arg hint shown in the header."""
    try:
        obj = json.loads(raw.strip())
        if not isinstance(obj, dict) or not obj:
            return ""
        # Prefer the most meaningful first value
        for key_pref in ("path", "file_path", "root_path", "query", "pattern",
                         "task", "input", "command", "url", "name"):
            for k, v in obj.items():
                if k == key_pref:
                    val = str(v).replace("\n", " ")
                    return (val[: max_len - 1] + "…") if len(val) > max_len else val
        # Fallback: first entry
        k, v = next(iter(obj.items()))
        val = str(v).replace("\n", " ")
        return (val[: max_len - 1] + "…") if len(val) > max_len else val
    except Exception:
        pass
    s = raw.strip()
    return (s[: max_len - 1] + "…") if len(s) > max_len else s


def _args_detail(raw: str) -> str:
    """Multiline key: value block for the expanded body."""
    try:
        obj = json.loads(raw.strip())
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                val = str(v)
                if "\n" in val:
                    n = val.count("\n") + 1
                    val = val.split("\n")[0] + f"  … ({n} lines)"
                if len(val) > 120:
                    val = val[:117] + "…"
                lines.append(f"  {k}: {val}")
            return "\n".join(lines)
    except Exception:
        pass
    s = raw.strip()
    return "  " + ((s[:300] + "…") if len(s) > 300 else s)


def _output_detail(raw: str) -> str:
    """Format output: up to 12 lines with overflow count."""
    lines = [ln for ln in (raw or "").strip().splitlines() if ln.strip()]
    if not lines:
        return "  (no output)"
    preview = "\n".join(f"  {ln}" for ln in lines[:12])
    if len(lines) > 12:
        preview += f"\n  … (+{len(lines) - 12} more lines)"
    if len(preview) > 900:
        preview = preview[:897] + "…"
    return preview


class ToolCallBlock(Widget):
    """
    Inline tool call widget — Claude Code style.

    While running:
        ◆  ⠸  read_file  /src/main.py  [0.3s]

    On success (click header to expand):
        ◆  ✓  read_file  /src/main.py  [0.3s]
        │   path: /src/main.py
        │   ─── output ───────────────────
        │   import asyncio
        │   … (+42 more lines)

    On error (same expand behaviour):
        ◆  ✗  read_file  /src/main.py  [0.3s]
    """

    DEFAULT_CSS = """
    ToolCallBlock {
        height: auto;
        padding: 0;
    }

    ToolCallBlock Label#tc-header {
        height: 1;
        padding: 0 0 0 1;
        color: $text-muted;
    }
    ToolCallBlock Label#tc-header:hover {
        background: $boost;
        color: $text;
    }
    ToolCallBlock.running  Label#tc-header { color: $secondary; }
    ToolCallBlock.success  Label#tc-header { color: $success; }
    ToolCallBlock.error    Label#tc-header { color: $error; }

    /* Body is hidden while running; shown by default after completion */
    ToolCallBlock Static#tc-body {
        display: none;
        height: auto;
        padding: 0 1 1 1;
        margin: 0 0 0 3;
        border-left: solid $panel-lighten-2;
        color: $text-muted;
    }
    ToolCallBlock.-expanded Static#tc-body {
        display: block;
    }

    /* When directly following a thinking block: collapse top gap */
    ToolCallBlock.-from-thinking {
        margin-top: 0;
        padding-top: 0;
    }
    /* Thinking-connected tool calls inherit the warning accent on their body border */
    ToolCallBlock.-from-thinking Static#tc-body {
        border-left: solid $warning-darken-2;
    }
    """

    def __init__(self, tool_name: str, input_summary: str, *, from_thinking: bool = False, **kwargs) -> None:
        cls = "running from-thinking" if from_thinking else "running"
        super().__init__(classes=cls, **kwargs)
        self._tool_name = tool_name
        self._input_raw = input_summary
        self._hint = _args_inline(input_summary)
        self._input_detail = _args_detail(input_summary)
        self._output_raw = ""
        self._start: float = 0.0
        self._spin_idx: int = 0
        self._timer: Timer | None = None
        self._done = False

    def compose(self) -> ComposeResult:
        yield Label(
            f"{_BULLET}  {_SPINNER[0]}  {self._tool_name}  {self._hint}",
            id="tc-header",
        )
        yield Static(self._input_detail, id="tc-body", markup=False)

    def on_mount(self) -> None:
        self._start = time.monotonic()
        self._timer = self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
        spin = _SPINNER[self._spin_idx]
        elapsed = _elapsed_str(time.monotonic() - self._start)
        with contextlib.suppress(Exception):
            self.query_one("#tc-header", Label).update(
                f"{_BULLET}  {spin}  {self._tool_name}  {self._hint}  {elapsed}"
            )

    def _stop_timer(self) -> None:
        if self._timer is not None:
            with contextlib.suppress(Exception):
                self._timer.stop()
            self._timer = None

    def on_click(self, event: Click) -> None:
        if self._done:
            self.toggle_class("-expanded")

    def set_result(self, output: str) -> None:
        """Mark success — expand body by default so output is immediately visible."""
        self._done = True
        self._output_raw = output
        elapsed = _elapsed_str(time.monotonic() - self._start)
        self._stop_timer()
        self.remove_class("running")
        self.add_class("success")
        self.add_class("-expanded")   # show output by default; click to collapse
        with contextlib.suppress(Exception):
            self.query_one("#tc-header", Label).update(
                f"{_BULLET}  {_ICON_OK}  {self._tool_name}  {self._hint}  {elapsed}"
            )
        self._refresh_body()

    def set_error(self, error: str) -> None:
        """Mark error — expand body by default so error is immediately visible."""
        self._done = True
        self._output_raw = error
        elapsed = _elapsed_str(time.monotonic() - self._start)
        self._stop_timer()
        self.remove_class("running")
        self.add_class("error")
        self.add_class("-expanded")   # show error by default; click to collapse
        with contextlib.suppress(Exception):
            self.query_one("#tc-header", Label).update(
                f"{_BULLET}  {_ICON_ERR}  {self._tool_name}  {self._hint}  {elapsed}"
            )
        self._refresh_body()

    def _refresh_body(self) -> None:
        output_section = ""
        if self._output_raw:
            output_section = "\n  ─── output ─────────────────────────\n" + _output_detail(
                self._output_raw
            )
        body_text = self._input_detail + output_section
        with contextlib.suppress(Exception):
            self.query_one("#tc-body", Static).update(body_text)
