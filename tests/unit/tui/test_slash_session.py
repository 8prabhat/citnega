"""
FR-UX-001 — TUI slash command tests for session lifecycle parity.

Tests: /rename, /delete, /show
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "s1", name: str = "test") -> Session:
    cfg = SessionConfig(
        session_id=session_id,
        name=name,
        framework="adk",
        default_model_id="m",
    )
    return Session(
        config=cfg,
        created_at=datetime.now(tz=UTC),
        last_active_at=datetime.now(tz=UTC),
        state=SessionState.IDLE,
        run_count=3,
    )


def _make_app_context(session_id: str = "s1") -> MagicMock:
    ctx = MagicMock()
    ctx._session_id = session_id
    ctx._messages: list[tuple[str, str]] = []

    async def _append(role, content):
        ctx._messages.append((role, content))

    ctx._append_message = _append
    ctx._app = MagicMock()
    ctx._app.screen = MagicMock()
    return ctx


def _make_service(session: Session | None = None) -> MagicMock:
    svc = MagicMock()
    svc.rename_session = AsyncMock()
    svc.delete_session = AsyncMock()
    svc.create_session = AsyncMock(return_value=session or _make_session("new-session"))
    svc.get_session = AsyncMock(return_value=session or _make_session())
    return svc


# ---------------------------------------------------------------------------
# /rename
# ---------------------------------------------------------------------------


class TestRenameCommand:
    @pytest.mark.asyncio
    async def test_rename_with_name(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import RenameCommand

        svc = _make_service()
        ctx = _make_app_context()
        cmd = RenameCommand(service=svc)
        await cmd.execute(["my-new-name"], ctx)

        svc.rename_session.assert_called_once_with("s1", "my-new-name")
        messages = [m[1] for m in ctx._messages]
        assert any("my-new-name" in m for m in messages)

    @pytest.mark.asyncio
    async def test_rename_multi_word_name(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import RenameCommand

        svc = _make_service()
        ctx = _make_app_context()
        cmd = RenameCommand(service=svc)
        await cmd.execute(["My", "Project", "Session"], ctx)

        svc.rename_session.assert_called_once_with("s1", "My Project Session")

    @pytest.mark.asyncio
    async def test_rename_no_args_shows_usage(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import RenameCommand

        svc = _make_service()
        ctx = _make_app_context()
        cmd = RenameCommand(service=svc)
        await cmd.execute([], ctx)

        svc.rename_session.assert_not_called()
        assert any("Usage" in m[1] for m in ctx._messages)

    @pytest.mark.asyncio
    async def test_rename_no_session(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import RenameCommand

        svc = _make_service()
        ctx = _make_app_context()
        ctx._session_id = None
        cmd = RenameCommand(service=svc)
        await cmd.execute(["new-name"], ctx)

        svc.rename_session.assert_not_called()
        assert any("No active session" in m[1] for m in ctx._messages)


# ---------------------------------------------------------------------------
# /delete
# ---------------------------------------------------------------------------


class TestDeleteSessionCommand:
    @pytest.mark.asyncio
    async def test_delete_without_yes_shows_confirmation(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import DeleteSessionCommand

        svc = _make_service()
        ctx = _make_app_context()
        cmd = DeleteSessionCommand(service=svc)
        await cmd.execute([], ctx)

        svc.delete_session.assert_not_called()
        # Should ask for confirmation
        assert any("--yes" in m[1] for m in ctx._messages)

    @pytest.mark.asyncio
    async def test_delete_with_yes_deletes_and_creates_new(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import DeleteSessionCommand

        new_sess = _make_session("new-id", "new-session")
        svc = _make_service(session=new_sess)
        ctx = _make_app_context("old-id")

        # Stub screen for NewSessionCommand path
        ctx._app.screen.action_clear_chat = MagicMock()

        cmd = DeleteSessionCommand(service=svc)
        await cmd.execute(["--yes"], ctx)

        svc.delete_session.assert_called_once_with("old-id")

    @pytest.mark.asyncio
    async def test_delete_no_session(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import DeleteSessionCommand

        svc = _make_service()
        ctx = _make_app_context()
        ctx._session_id = None
        cmd = DeleteSessionCommand(service=svc)
        await cmd.execute(["--yes"], ctx)

        svc.delete_session.assert_not_called()
        assert any("No active" in m[1] for m in ctx._messages)


# ---------------------------------------------------------------------------
# /show
# ---------------------------------------------------------------------------


class TestShowSessionCommand:
    @pytest.mark.asyncio
    async def test_show_displays_session_fields(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import ShowSessionCommand

        session = _make_session("abc-123", "my-session")
        svc = _make_service(session=session)
        ctx = _make_app_context("abc-123")
        cmd = ShowSessionCommand(service=svc)
        await cmd.execute([], ctx)

        messages = [m[1] for m in ctx._messages]
        combined = "\n".join(messages)
        assert "abc-123" in combined
        assert "my-session" in combined
        assert "framework" in combined
        assert "runs" in combined

    @pytest.mark.asyncio
    async def test_show_no_session(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import ShowSessionCommand

        svc = _make_service()
        ctx = _make_app_context()
        ctx._session_id = None
        cmd = ShowSessionCommand(service=svc)
        await cmd.execute([], ctx)

        assert any("No active session" in m[1] for m in ctx._messages)

    @pytest.mark.asyncio
    async def test_show_session_not_found(self) -> None:
        from citnega.apps.tui.slash_commands.builtin import ShowSessionCommand

        svc = _make_service()
        svc.get_session = AsyncMock(return_value=None)
        ctx = _make_app_context()
        cmd = ShowSessionCommand(service=svc)
        await cmd.execute([], ctx)

        assert any("not found" in m[1].lower() for m in ctx._messages)
