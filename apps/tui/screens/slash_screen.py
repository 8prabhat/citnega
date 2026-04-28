"""SlashCommandScreen — modal screen for slash command selection.

A ModalScreen has full ownership of key events:
  - Up / Down navigate the list (priority bindings intercept before Input processes them)
  - Enter executes the highlighted command
  - Escape cancels (screen dismisses with None)
  - Any other character goes to the filter Input → live filtering

Caller receives the selected command name (str) or None on cancel via
the standard push_screen callback.
"""

from __future__ import annotations

import contextlib

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView

# ── Category metadata ─────────────────────────────────────────────────────────

_CATEGORY_ORDER = ["SESSION", "MODE", "AGENTS", "SKILLS", "WORKSPACE", "UTILITY"]

_COMMAND_CATEGORIES: dict[str, str] = {
    "new": "SESSION", "sessions": "SESSION", "rename": "SESSION",
    "delete": "SESSION", "show": "SESSION", "compact": "SESSION",
    "mode": "MODE", "model": "MODE", "think": "MODE",
    "agent": "AGENTS", "approve": "AGENTS", "cancel": "AGENTS",
    "skills": "SKILLS", "skill": "SKILLS",
    "setworkfolder": "WORKSPACE", "refresh": "WORKSPACE",
    "createtool": "WORKSPACE", "createagent": "WORKSPACE",
    "createworkflow": "WORKSPACE", "createskill": "WORKSPACE",
    "creatementalmodel": "WORKSPACE",
    "help": "UTILITY", "clear": "UTILITY", "setup": "UTILITY",
}

_CATEGORY_ICONS = {
    "SESSION": "◆ SESSION", "MODE": "◆ MODE", "AGENTS": "◆ AGENTS",
    "SKILLS": "◆ SKILLS", "WORKSPACE": "◆ WORKSPACE",
    "UTILITY": "◆ UTILITY", "OTHER": "◆ OTHER",
}


class SlashCommandScreen(ModalScreen[str | None]):
    """
    Modal overlay for browsing and executing slash commands.

    Dismisses with the selected command name (str) or None on cancel.
    """

    DEFAULT_CSS = """
    SlashCommandScreen {
        align: left bottom;
    }

    #slash-panel {
        width: 72;
        height: 22;
        margin-bottom: 7;
        margin-left: 1;
        border: solid $accent;
        background: $surface;
    }

    #slash-header {
        height: 1;
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
    }

    #slash-filter {
        height: 3;
        border: none;
        border-bottom: solid $accent-darken-2;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #slash-list {
        height: 1fr;
    }

    SlashCommandScreen .category-sep {
        background: $panel-darken-1;
        color: $text-muted;
        height: 1;
        padding: 0 1;
    }

    SlashCommandScreen .cmd-item {
        height: 1;
        padding: 0 1;
    }

    SlashCommandScreen .cmd-item.--highlight {
        background: $accent-darken-1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_none",  "Close"),
        Binding("up",     "cursor_up",     show=False, priority=True),
        Binding("down",   "cursor_down",   show=False, priority=True),
        Binding("enter",  "select_cmd",    show=False, priority=True),
    ]

    def __init__(self, commands: list[tuple[str, str]], initial_filter: str = "") -> None:
        super().__init__()
        self._commands = commands
        self._initial_filter = initial_filter

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Vertical(id="slash-panel"):
            yield Label(
                "  / commands — type to filter — ↑↓ navigate — ↵ execute — Esc cancel",
                id="slash-header",
            )
            yield Input(
                value=self._initial_filter,
                placeholder="filter...",
                id="slash-filter",
            )
            yield ListView(id="slash-list")

    def on_mount(self) -> None:
        self._rebuild(self._initial_filter)
        self.query_one("#slash-filter", Input).focus()

    # ── Navigation actions (priority=True — fire before Input sees Up/Down/Enter) ─

    def action_cursor_up(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one(ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one(ListView).action_cursor_down()

    def action_select_cmd(self) -> None:
        with contextlib.suppress(Exception):
            lv = self.query_one(ListView)
            item = lv.highlighted_child
            if item is None:
                return
            item_id = item.id or ""
            if item_id.startswith("slash-"):
                self.dismiss(item_id.removeprefix("slash-"))

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    # ── Live filter ───────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        self._rebuild(event.value)

    # ── List rebuild ──────────────────────────────────────────────────────────

    def _rebuild(self, filter_text: str = "") -> None:
        with contextlib.suppress(Exception):
            lv = self.query_one("#slash-list", ListView)

            q = filter_text.lower().strip()
            matches = [
                (n, h) for n, h in self._commands
                if not q or n.startswith(q) or q in n
            ]

            lv.clear()

            if not matches:
                lv.append(ListItem(Label("  [dim]no matching commands[/dim]"), id="no-match"))
                return

            groups: dict[str, list[tuple[str, str]]] = {}
            for name, help_text in matches:
                cat = _COMMAND_CATEGORIES.get(name, "OTHER")
                groups.setdefault(cat, []).append((name, help_text))

            ordered: list[tuple[str, list[tuple[str, str]]]] = []
            for cat in _CATEGORY_ORDER:
                if cat in groups:
                    ordered.append((cat, groups.pop(cat)))
            for cat, items in groups.items():
                ordered.append((cat, items))

            for cat, items in ordered:
                icon = _CATEGORY_ICONS.get(cat, f"◆ {cat}")
                lv.append(ListItem(
                    Label(f"[bold dim]{icon}[/bold dim]"),
                    classes="category-sep",
                    id=f"sep-{cat.lower()}",
                ))
                for name, help_text in items:
                    desc = (help_text or "")[:48]
                    line = f"  [bold cyan]/{name:<16}[/bold cyan] [dim]{desc}[/dim]"
                    lv.append(ListItem(Label(line), classes="cmd-item", id=f"slash-{name}"))

            # Highlight the first selectable item
            self._highlight_first(lv)

    def _highlight_first(self, lv: ListView) -> None:
        with contextlib.suppress(Exception):
            for item in lv.query(ListItem):
                if (item.id or "").startswith("slash-"):
                    lv.index = lv._nodes.index(item)  # type: ignore[attr-defined]
                    break
