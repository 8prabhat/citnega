"""SlashCommandPopup — live-filter, grouped, scrollable slash command overlay.

UX matches Claude Code:
  - Opens automatically when user types "/" in the input
  - Filters in real time as more characters are typed
  - Arrow keys navigate, Enter selects, Escape dismisses
  - Commands grouped by category with visual separators
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView

if TYPE_CHECKING:
    from textual.app import ComposeResult

# Category order shown in the popup
_CATEGORY_ORDER = ["SESSION", "MODE", "AGENTS", "SKILLS", "WORKSPACE", "UTILITY"]

# Maps command name → display category
COMMAND_CATEGORIES: dict[str, str] = {
    # SESSION
    "new":            "SESSION",
    "sessions":       "SESSION",
    "rename":         "SESSION",
    "delete":         "SESSION",
    "show":           "SESSION",
    "compact":        "SESSION",
    # MODE
    "mode":           "MODE",
    "model":          "MODE",
    "think":          "MODE",
    # AGENTS
    "agent":          "AGENTS",
    "approve":        "AGENTS",
    "cancel":         "AGENTS",
    # SKILLS
    "skills":         "SKILLS",
    "skill":          "SKILLS",
    # WORKSPACE
    "setworkfolder":  "WORKSPACE",
    "refresh":        "WORKSPACE",
    "createtool":     "WORKSPACE",
    "createagent":    "WORKSPACE",
    "createworkflow": "WORKSPACE",
    "createskill":    "WORKSPACE",
    "creatementalmodel": "WORKSPACE",
    # UTILITY
    "help":           "UTILITY",
    "clear":          "UTILITY",
}

_CATEGORY_ICONS = {
    "SESSION":   "◆ SESSION",
    "MODE":      "◆ MODE",
    "AGENTS":    "◆ AGENTS",
    "SKILLS":    "◆ SKILLS",
    "WORKSPACE": "◆ WORKSPACE",
    "UTILITY":   "◆ UTILITY",
    "OTHER":     "◆ OTHER",
}


class SlashCommandPopup(Widget):
    """
    Floating overlay listing slash commands with live filtering and grouping.

    Call ``update_filter(prefix)`` whenever the text after "/" changes.
    The popup rebuilds its list in-place without remounting.
    """

    DEFAULT_CSS = """
    SlashCommandPopup {
        layer: overlay;
        dock: bottom;
        height: 18;
        width: 72;
        margin-bottom: 4;
        margin-left: 1;
        border: solid $accent;
        background: $surface;
    }

    SlashCommandPopup #popup-header {
        height: 1;
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
    }

    SlashCommandPopup #popup-list {
        height: 1fr;
    }

    SlashCommandPopup .category-sep {
        background: $panel-darken-1;
        color: $text-muted;
        height: 1;
        padding: 0 1;
    }

    SlashCommandPopup .cmd-item {
        height: 1;
        padding: 0 1;
    }

    SlashCommandPopup .cmd-item:hover {
        background: $accent-darken-1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
        Binding("up",     "cursor_up",   "Up",   show=False),
        Binding("down",   "cursor_down", "Down", show=False),
    ]

    def __init__(
        self,
        commands: list[tuple[str, str]],
        **kwargs,
    ) -> None:
        """
        Args:
            commands: ``[(name, help_text), ...]`` — full unfiltered list.
        """
        super().__init__(**kwargs)
        self._all_commands = commands
        self._filter = ""

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Label("  / commands  —  type to filter  —  ↑↓ navigate  —  ↵ select", id="popup-header")
        yield ListView(id="popup-list")

    def on_mount(self) -> None:
        self._rebuild()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_filter(self, prefix: str) -> None:
        """Called by controller whenever the text after '/' changes."""
        if prefix != self._filter:
            self._filter = prefix
            self._rebuild()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        """Rebuild the ListView contents for the current filter."""
        import contextlib

        lv = self.query_one("#popup-list", ListView)

        # Filter commands
        q = self._filter.lower().strip()
        if q:
            matches = [(n, h) for n, h in self._all_commands if n.startswith(q) or q in n]
        else:
            matches = list(self._all_commands)

        if not matches:
            with contextlib.suppress(Exception):
                lv.clear()
                lv.append(ListItem(Label("  [dim]no matching commands[/dim]"), id="no-match"))
            return

        # Group by category
        groups: dict[str, list[tuple[str, str]]] = {}
        for name, help_text in matches:
            cat = COMMAND_CATEGORIES.get(name, "OTHER")
            groups.setdefault(cat, []).append((name, help_text))

        # Build ordered list preserving category order
        ordered: list[tuple[str, list[tuple[str, str]]]] = []
        for cat in _CATEGORY_ORDER:
            if cat in groups:
                ordered.append((cat, groups.pop(cat)))
        for cat, items in groups.items():
            ordered.append((cat, items))

        # Rebuild ListView items
        new_items: list[ListItem] = []
        for cat, items in ordered:
            # Category header (not selectable — no id with slash- prefix)
            header_label = _CATEGORY_ICONS.get(cat, f"◆ {cat}")
            new_items.append(
                ListItem(
                    Label(f"[bold dim]{header_label}[/bold dim]"),
                    classes="category-sep",
                    id=f"sep-{cat.lower()}",
                )
            )
            for name, help_text in items:
                desc = (help_text or "")[:48]
                line = f"  [bold cyan]/{name:<16}[/bold cyan] [dim]{desc}[/dim]"
                new_items.append(
                    ListItem(Label(line), classes="cmd-item", id=f"slash-{name}")
                )

        with contextlib.suppress(Exception):
            lv.clear()
            for item in new_items:
                lv.append(item)

            # Focus first selectable item
            self._focus_first_cmd(lv)

    def _focus_first_cmd(self, lv: ListView) -> None:
        import contextlib
        with contextlib.suppress(Exception):
            for item in lv.query(ListItem):
                if (item.id or "").startswith("slash-"):
                    lv.index = lv._nodes.index(item)  # type: ignore[attr-defined]
                    break

    # ── Selection ────────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if not item_id.startswith("slash-"):
            return  # category separator — ignore
        cmd_name = item_id.removeprefix("slash-")
        self._insert_command(cmd_name)

    def _insert_command(self, cmd_name: str) -> None:
        from textual.widgets import Input

        try:
            inp = self.app.query_one("#chat-input", Input)
            inp.value = f"/{cmd_name} "
            inp.cursor_position = len(inp.value)
            inp.focus()
        except Exception:
            pass

        self._close()

    def _close(self) -> None:
        try:
            ctrl = getattr(self.app, "_controller", None)
            if ctrl is not None:
                ctrl.dismiss_popup()
            else:
                self.remove()
        except Exception:
            pass

    # ── Bindings ─────────────────────────────────────────────────────────────

    def action_dismiss(self) -> None:
        self._close()

    def action_cursor_up(self) -> None:
        import contextlib
        with contextlib.suppress(Exception):
            lv = self.query_one("#popup-list", ListView)
            lv.action_cursor_up()

    def action_cursor_down(self) -> None:
        import contextlib
        with contextlib.suppress(Exception):
            lv = self.query_one("#popup-list", ListView)
            lv.action_cursor_down()
