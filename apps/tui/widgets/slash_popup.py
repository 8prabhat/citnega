"""SlashCommandPopup — live-filter, grouped, scrollable slash command overlay.

Navigation model
----------------
Focus stays in SmartInput's TextArea the whole time. ChatScreen has priority
bindings for Up / Down / Enter that fire *before* Textual forwards the event
to TextArea, so popup navigation works without any focus juggling:

  Up / Down  → ChatScreen.action_popup_up / _popup_down → cursor_up / cursor_down
  Enter      → ChatScreen.action_popup_select → _select_current → _insert_command
  Escape     → ChatScreen.action_dismiss_popup (existing binding)
  Chars      → fall through to TextArea → SmartInput.Changed → update_filter
"""

from __future__ import annotations

import contextlib
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
    "setup":          "UTILITY",
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

    Focus stays in SmartInput/TextArea. Navigation is handled by ChatScreen
    priority bindings — see module docstring.
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
    ]

    def __init__(
        self,
        commands: list[tuple[str, str]],
        **kwargs,
    ) -> None:
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

    # ── Cursor navigation (called by ChatScreen priority actions) ─────────────

    def action_cursor_up(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one(ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one(ListView).action_cursor_down()

    def _select_current(self) -> None:
        """Execute the currently highlighted command."""
        with contextlib.suppress(Exception):
            lv = self.query_one(ListView)
            item = lv.highlighted_child
            if item is None:
                return
            item_id = item.id or ""
            if item_id.startswith("slash-"):
                self._insert_command(item_id.removeprefix("slash-"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        lv = self.query_one("#popup-list", ListView)

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

        groups: dict[str, list[tuple[str, str]]] = {}
        for name, help_text in matches:
            cat = COMMAND_CATEGORIES.get(name, "OTHER")
            groups.setdefault(cat, []).append((name, help_text))

        ordered: list[tuple[str, list[tuple[str, str]]]] = []
        for cat in _CATEGORY_ORDER:
            if cat in groups:
                ordered.append((cat, groups.pop(cat)))
        for cat, items in groups.items():
            ordered.append((cat, items))

        new_items: list[ListItem] = []
        for cat, items in ordered:
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
            self._focus_first_cmd(lv)

    def _focus_first_cmd(self, lv: ListView) -> None:
        with contextlib.suppress(Exception):
            for item in lv.query(ListItem):
                if (item.id or "").startswith("slash-"):
                    lv.index = lv._nodes.index(item)  # type: ignore[attr-defined]
                    break

    # ── Selection ────────────────────────────────────────────────────────────

    def _insert_command(self, cmd_name: str) -> None:
        from citnega.apps.tui.widgets.smart_input import SmartInput

        # Suppress the TextArea.Changed that load_text fires below, so
        # on_input_value_changed does not re-open the popup.
        ctrl = getattr(self.app, "_controller", None)
        if ctrl is not None:
            ctrl._suppress_popup_for_next_change = True

        self._close()

        try:
            smart = self.app.query_one("#chat-input", SmartInput)
            smart._textarea.load_text(f"/{cmd_name}")
            smart._textarea.focus()
            # Submit via the same path as Ctrl+Enter.
            smart.post_message(SmartInput.Submitted(input=smart))
        except Exception:
            pass

    def _close(self) -> None:
        try:
            ctrl = getattr(self.app, "_controller", None)
            if ctrl is not None:
                ctrl.dismiss_popup()
            else:
                self.remove()
        except Exception:
            pass
        try:
            from citnega.apps.tui.widgets.smart_input import SmartInput
            smart = self.app.query_one("#chat-input", SmartInput)
            self.app.call_after_refresh(smart._textarea.focus)
        except Exception:
            pass

    def action_dismiss(self) -> None:
        self._close()
