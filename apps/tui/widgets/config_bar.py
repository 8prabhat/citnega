"""
ConfigBar — one-line settings strip inside the bottom panel.

Shows ONLY static configuration values that are not already displayed by
ContextBar.  ContextBar owns: session name, model, framework, mode, think,
workfolder, token budget, run state.

ConfigBar owns (8 values, no overlap):
  rounds | depth | local | policy | retries | compact+threshold | cb | F2-hint

This strict split means the user never sees the same datum twice.
"""

from __future__ import annotations

import contextlib

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label


def _bool_label(value: bool) -> str:
    return "[green]on[/green]" if value else "[dim]off[/dim]"


def _load_config_line() -> str:
    """Return a single compact line with the 8 non-overlapping config values."""
    sep = "  [dim]│[/dim]  "

    # Defaults
    max_rounds = 5
    depth = 2
    local_only = True
    policy = "dev"
    retries = 3
    s_retries = 2
    auto_compact = True
    compact_at = 50
    cb_thresh = 5

    try:
        from citnega.packages.config.loaders import load_settings
        s = load_settings()
        max_rounds   = s.runtime.max_tool_rounds
        depth        = s.runtime.max_callable_depth
        local_only   = s.runtime.local_only
        policy       = s.policy.template
        retries      = s.runtime.provider_max_retries
        s_retries    = s.runtime.streaming_max_retries
        auto_compact = s.conversation.auto_compact
        compact_at   = s.conversation.compact_threshold_messages
        cb_thresh    = s.runtime.circuit_breaker_threshold
    except Exception:
        pass

    compact_str = _bool_label(auto_compact)
    if auto_compact and compact_at > 0:
        compact_str += f" @{compact_at}msg"

    parts = [
        f"[bold dim]⚙ CFG[/bold dim]",
        f"rounds:{max_rounds}",
        f"depth:{depth}",
        f"local:{_bool_label(local_only)}",
        f"policy:{policy}",
        f"retries:{retries}/{s_retries}",
        f"compact:{compact_str}",
        f"cb:{cb_thresh}",
        "[dim]F2=edit[/dim]",
    ]
    return sep.join(parts)


class ConfigBar(Widget):
    """
    Single-line settings strip — sits between SmartInput and ContextBar.

    Shows 8 configuration values that ContextBar does NOT show.
    Call ``refresh_config()`` after saving settings so the display updates
    immediately without a restart.
    """

    DEFAULT_CSS = """
    ConfigBar {
        height: 1;
        background: $panel-darken-1;
        color: $text-disabled;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="cfg-line")

    def on_mount(self) -> None:
        self.refresh_config()

    def refresh_config(self) -> None:
        """Re-read settings and update the display line."""
        try:
            line = _load_config_line()
            with contextlib.suppress(Exception):
                self.query_one("#cfg-line", Label).update(line)
        except Exception:
            pass
