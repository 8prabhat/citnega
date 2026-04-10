"""
SessionPickerScreen — shown at startup so the user can resume, create, or
delete past sessions.

Keybindings
-----------
  Enter / r   Resume selected session
  n           New session (skip picker)
  d           Delete selected session
  q / Escape  Quit application

The screen calls back into the parent App via a custom message so the App can
act without needing to import this screen directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

if TYPE_CHECKING:
    from citnega.packages.protocol.models.sessions import Session


class SessionPickerScreen(Screen):
    """Startup screen listing all previous sessions."""

    BINDINGS = [
        Binding("enter",  "resume",      "Resume",     show=True),
        Binding("r",      "resume",      "Resume",     show=False),
        Binding("n",      "new_session", "New session",show=True),
        Binding("d",      "delete",      "Delete",     show=True),
        Binding("q",      "app.quit",    "Quit",       show=True),
        Binding("escape", "app.quit",    "Quit",       show=False),
    ]

    DEFAULT_CSS = """
    SessionPickerScreen {
        layout: vertical;
    }
    #picker-hint {
        color: $text-muted;
        text-align: center;
        height: 1;
        margin-top: 1;
    }
    #sessions-table {
        height: 1fr;
        margin: 1 2;
    }
    """

    # ── Messages ──────────────────────────────────────────────────────────────

    class SessionSelected(Message):
        """User wants to resume *session_id*."""
        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class NewSessionRequested(Message):
        """User wants a brand-new session."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self, sessions: list["Session"], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sessions: list["Session"] = sessions

    def compose(self) -> ComposeResult:
        yield Header()
        if not self._sessions:
            yield Label(
                "No previous sessions found. Press [bold]n[/bold] to start a new one.",
                id="picker-hint",
            )
        else:
            yield Label(
                "Select a session to resume, or press [bold]n[/bold] for a new one.",
                id="picker-hint",
            )
            table: DataTable = DataTable(id="sessions-table", cursor_type="row")
            table.add_columns("Name", "ID", "Last Active", "Messages", "Mode")
            for s in self._sessions:
                last = s.last_active_at
                if isinstance(last, datetime):
                    age = _format_age(last)
                else:
                    age = str(last)[:16]
                # Try to get extra info from config
                mode = getattr(s.config, "mode_name", "chat")
                table.add_row(
                    s.config.name or "(unnamed)",
                    s.config.session_id[:8] + "…",
                    age,
                    "",      # message count not available here; shown as blank
                    mode,
                    key=s.config.session_id,
                )
            yield table
        yield Footer()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_resume(self) -> None:
        if not self._sessions:
            return
        try:
            table = self.query_one(DataTable)
            row_key = table.get_row_at(table.cursor_row)
            session_id = table.get_cell_at((table.cursor_row, 0))
        except Exception:
            return
        # The key we passed to add_row is the full session_id
        try:
            table    = self.query_one(DataTable)
            row_key  = table.cursor_row
            # The first visible column is name — find the session by matching table key
            # DataTable keys are the 'key' arg passed to add_row
            if row_key < len(self._sessions):
                sid = self._sessions[row_key].config.session_id
                self.post_message(self.SessionSelected(sid))
        except Exception:
            pass

    def action_new_session(self) -> None:
        self.post_message(self.NewSessionRequested())

    def action_delete(self) -> None:
        if not self._sessions:
            return
        try:
            table   = self.query_one(DataTable)
            row_key = table.cursor_row
            if row_key < len(self._sessions):
                session = self._sessions[row_key]
                self._sessions.pop(row_key)
                table.remove_row(session.config.session_id)
                # Schedule async delete via app
                import asyncio  # noqa: PLC0415
                asyncio.get_event_loop().create_task(
                    self._delete_session(session.config.session_id)
                )
                if not self._sessions:
                    self.notify("No sessions left. Press n to start a new one.")
        except Exception as exc:
            self.notify(f"Delete failed: {exc}", severity="error")

    async def _delete_session(self, session_id: str) -> None:
        app = self.app
        service = getattr(app, "service", None)
        if service is not None:
            try:
                await service.delete_session(session_id)
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_age(dt: datetime) -> str:
    """Return a human-readable age string like '2h ago' or '3d ago'."""
    now   = datetime.now(tz=timezone.utc)
    delta = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    secs  = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"
