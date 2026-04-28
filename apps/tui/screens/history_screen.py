"""
HistoryScreen — F3 screen showing all past sessions for quick resume.

Layout:
    ┌── ◎ History ──────────────────────────────────────────────┐
    │  [search filter input]                                    │
    ├────────────────────────────────────────────────────────────┤
    │  Session Name   │ Mode      │ Model    │ Last Active       │
    │  my-project     │ code      │ claude-… │ 2m ago            │
    │  ai-research    │ auto_res  │ claude-… │ 1h ago            │
    ├────────────────────────────────────────────────────────────┤
    │  [Enter] Load   [Esc] Back   [F5] Refresh                 │
    └────────────────────────────────────────────────────────────┘

Bindings:
  Enter   Load selected session
  Escape  Back to chat
  F5      Refresh the list
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Label

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from citnega.packages.protocol.models.sessions import Session


class HistoryScreen(Screen):
    """All-sessions history screen — select a row and press Enter to resume."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back",    show=True),
        Binding("enter",  "load_session",   "Load",    show=True),
        Binding("f5",     "refresh_list",   "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    HistoryScreen {
        layout: vertical;
    }
    #history-filter {
        margin: 1 2 0 2;
        height: 3;
    }
    #history-table {
        height: 1fr;
        margin: 0 2 1 2;
    }
    #history-hint {
        color: $text-muted;
        text-align: center;
        height: 1;
        margin-top: 1;
    }
    """

    # ── Messages ──────────────────────────────────────────────────────────────

    class SessionSelected(Message):
        """User wants to resume *session_id*."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, service: object | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service
        self._sessions: list[Session] = []
        self._filtered: list[Session] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Input(placeholder="Filter sessions…", id="history-filter")
        yield Label(
            "Loading sessions…",
            id="history-hint",
        )
        table: DataTable = DataTable(id="history-table", cursor_type="row")
        table.add_columns("Name", "ID", "Mode", "Model", "Last Active")
        yield table
        yield Footer()

    async def on_mount(self) -> None:
        await self._load_sessions()

    # ── Data loading ──────────────────────────────────────────────────────────

    async def _load_sessions(self) -> None:
        if self._service is not None:
            try:
                self._sessions = await self._service.list_sessions(limit=200)
                self._sessions.sort(
                    key=lambda s: s.last_active_at or "",
                    reverse=True,
                )
            except Exception as exc:
                self.notify(f"Could not load sessions: {exc}", severity="warning")
                self._sessions = []

        self._filtered = list(self._sessions)
        self._populate_table()

        hint = self.query_one("#history-hint", Label)
        if self._sessions:
            hint.update(f"{len(self._sessions)} sessions — select one and press [bold]Enter[/bold] to load")
        else:
            hint.update("No sessions found.")

    def _populate_table(self, filter_text: str = "") -> None:
        table = self.query_one(DataTable)
        table.clear()

        lower = filter_text.lower().strip()
        if lower:
            self._filtered = [
                s for s in self._sessions
                if lower in (s.config.name or "").lower()
                or lower in s.config.session_id.lower()
                or lower in getattr(s.config, "mode_name", "").lower()
            ]
        else:
            self._filtered = list(self._sessions)

        for s in self._filtered:
            last = s.last_active_at
            if isinstance(last, datetime):
                age = _format_age(last)
            elif last:
                age = str(last)[:16]
            else:
                age = "—"

            mode = getattr(s.config, "mode_name", "") or "chat"
            model = getattr(s.config, "default_model_id", "") or "—"
            if len(model) > 12:
                model = model[:11] + "…"

            table.add_row(
                s.config.name or "(unnamed)",
                s.config.session_id[:8] + "…",
                mode,
                model,
                age,
                key=s.config.session_id,
            )

    # ── Input filter ──────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate_table(filter_text=event.value)

    # ── DataTable row selection ───────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_load_session()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_load_session(self) -> None:
        if not self._filtered:
            return
        try:
            table = self.query_one(DataTable)
            row_idx = table.cursor_row
            if 0 <= row_idx < len(self._filtered):
                sid = self._filtered[row_idx].config.session_id
                self.post_message(self.SessionSelected(sid))
        except Exception as exc:
            self.notify(f"Could not load session: {exc}", severity="error")

    async def action_refresh_list(self) -> None:
        hint = self.query_one("#history-hint", Label)
        hint.update("Refreshing…")
        await self._load_sessions()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_age(dt: datetime) -> str:
    now = datetime.now(tz=UTC)
    delta = now - dt.replace(tzinfo=UTC) if dt.tzinfo is None else now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"
