"""AgentCallBlock — animated sidebar card for a single agent invocation."""

from __future__ import annotations

import contextlib
import json
import time
from typing import TYPE_CHECKING

from textual.widget import Widget
from textual.widgets import Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_STAR_ON  = "✦"
_STAR_OFF = "✧"
_ICON_OK  = "✓"
_ICON_ERR = "✗"


def _parse_input(raw: str) -> str:
    stripped = raw.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                val = str(v)
                if len(val) > 80:
                    val = val[:77] + "…"
                lines.append(f"  {k}: {val}")
            return "\n".join(lines) if lines else stripped
    except Exception:
        pass
    return stripped[:200] if len(stripped) > 200 else stripped


class AgentCallBlock(Widget):
    """
    Animated agent-invocation card in the sidebar.

    Visually distinct from ToolCallBlock: accent colour border + "[agent]" prefix.

    Layout:
      ┌ header:  ✦ ⠼  [agent] agent_name         [0.0s]
      │ task:    key: value
      │ result:  (hidden until done)
      └──────────────────────────────────────────────────
    """

    DEFAULT_CSS = """
    AgentCallBlock {
        height: auto;
        margin: 1 0 0 0;
        padding: 0 1 1 1;
        border-left: thick $panel-lighten-3;
        background: $panel;
    }

    /* ── running ──────────────────────────────────────── */
    AgentCallBlock.running      { border-left: thick $accent; }
    AgentCallBlock.running #ac-header { color: $accent; }

    /* ── success ──────────────────────────────────────── */
    AgentCallBlock.success      { border-left: thick $success; }
    AgentCallBlock.success #ac-header { color: $success; }

    /* ── error ────────────────────────────────────────── */
    AgentCallBlock.error        { border-left: thick $error; }
    AgentCallBlock.error #ac-header { color: $error; }

    /* ── shared ───────────────────────────────────────── */
    AgentCallBlock #ac-header {
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }
    AgentCallBlock #ac-input {
        color: $text-disabled;
        text-style: italic;
        height: auto;
        margin: 0;
        padding: 0;
    }
    AgentCallBlock #ac-output {
        color: $text-muted;
        height: auto;
        margin: 1 0 0 0;
        padding: 0;
    }
    """

    def __init__(self, agent_name: str, input_summary: str, **kwargs) -> None:
        super().__init__(classes="running", **kwargs)
        self._agent_name = agent_name
        self._input_summary = input_summary
        self._start: float = 0.0
        self._spin_idx: int = 0
        self._star_on: bool = True
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Label(
            f"{_STAR_ON} {_SPINNER[0]}  [agent] {self._agent_name}",
            id="ac-header",
        )
        parsed = _parse_input(self._input_summary)
        yield Static(parsed or "—", id="ac-input", markup=False)
        out = Static("", id="ac-output", markup=False)
        out.display = False
        yield out

    def on_mount(self) -> None:
        self._start = time.monotonic()
        self._timer = self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        self._spin_idx = (self._spin_idx + 1) % len(_SPINNER)
        if self._spin_idx % 5 == 0:
            self._star_on = not self._star_on
        star = _STAR_ON if self._star_on else _STAR_OFF
        spin = _SPINNER[self._spin_idx]
        elapsed = time.monotonic() - self._start
        elapsed_str = f"[{elapsed:.1f}s]"
        with contextlib.suppress(Exception):
            self.query_one("#ac-header", Label).update(
                f"{star} {spin}  [agent] {self._agent_name}  {elapsed_str}"
            )

    def _stop_timer(self) -> None:
        if self._timer is not None:
            with contextlib.suppress(Exception):
                self._timer.stop()
            self._timer = None

    def set_result(self, output: str) -> None:
        elapsed = time.monotonic() - self._start
        self._stop_timer()
        self.remove_class("running")
        self.add_class("success")
        with contextlib.suppress(Exception):
            self.query_one("#ac-header", Label).update(
                f"{_ICON_OK}  [agent] {self._agent_name}  [{elapsed:.1f}s]"
            )
        self._show_output(output)

    def set_error(self, error: str) -> None:
        elapsed = time.monotonic() - self._start
        self._stop_timer()
        self.remove_class("running")
        self.add_class("error")
        with contextlib.suppress(Exception):
            self.query_one("#ac-header", Label).update(
                f"{_ICON_ERR}  [agent] {self._agent_name}  [{elapsed:.1f}s]"
            )
        self._show_output(error or "unknown error")

    # ── internal ──────────────────────────────────────────────────────────────

    def _show_output(self, text: str) -> None:
        lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
        preview = "\n".join(lines[:5])
        if len(lines) > 5:
            preview += f"\n  … (+{len(lines) - 5} more lines)"
        if len(preview) > 400:
            preview = preview[:397] + "…"
        with contextlib.suppress(Exception):
            out = self.query_one("#ac-output", Static)
            out.update(preview or "(no output)")
            out.display = True
