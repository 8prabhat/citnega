"""
FR-UX-001 — CLI session lifecycle parity tests.

Tests: session rename, session show, session list, session new, session delete.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "test-id", name: str = "test"):
    from datetime import UTC, datetime

    from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState

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
        run_count=2,
    )


_UNSET = object()


def _cli_bootstrap_ctx(session=_UNSET, sessions=_UNSET):
    """Return a context manager that yields a stub ApplicationService."""
    import contextlib

    svc = MagicMock()
    svc.get_session = AsyncMock(return_value=_make_session() if session is _UNSET else session)
    svc.list_sessions = AsyncMock(
        return_value=[_make_session()] if sessions is _UNSET else sessions
    )
    svc.create_session = AsyncMock(return_value=_make_session("new-id"))
    svc.delete_session = AsyncMock()
    svc.rename_session = AsyncMock()

    @contextlib.asynccontextmanager
    async def _ctx():
        yield svc

    return _ctx


# ---------------------------------------------------------------------------
# session rename
# ---------------------------------------------------------------------------


class TestSessionRenameCommand:
    def test_rename_success(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        session = _make_session("abc-123", "old-name")
        ctx = _cli_bootstrap_ctx(session=session)

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["rename", "abc-123", "new-name"])

        assert result.exit_code == 0
        assert "new-name" in result.output

    def test_rename_session_not_found(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        ctx = _cli_bootstrap_ctx(session=None)

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["rename", "missing-id", "new-name"])

        assert result.exit_code != 0

    def test_rename_calls_service(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        session = _make_session("the-id", "old")

        svc = MagicMock()
        svc.get_session = AsyncMock(return_value=session)
        svc.rename_session = AsyncMock()

        import contextlib

        @contextlib.asynccontextmanager
        async def _ctx():
            yield svc

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", _ctx):
            runner.invoke(app, ["rename", "the-id", "brand-new"])

        svc.rename_session.assert_called_once_with("the-id", "brand-new")


# ---------------------------------------------------------------------------
# session show
# ---------------------------------------------------------------------------


class TestSessionShowCommand:
    def test_show_prints_fields(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        session = _make_session("xyz-789", "my-session")
        ctx = _cli_bootstrap_ctx(session=session)

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["show", "xyz-789"])

        assert result.exit_code == 0
        assert "xyz-789" in result.output
        assert "my-session" in result.output
        assert "framework" in result.output

    def test_show_not_found_exits_nonzero(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        ctx = _cli_bootstrap_ctx(session=None)

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["show", "no-such-id"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# session list
# ---------------------------------------------------------------------------


class TestSessionListCommand:
    def test_list_shows_sessions(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        sessions = [_make_session("id1", "session-one"), _make_session("id2", "session-two")]
        ctx = _cli_bootstrap_ctx(sessions=sessions)

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "id1" in result.output
        assert "id2" in result.output

    def test_list_empty(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        ctx = _cli_bootstrap_ctx(sessions=[])

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", ctx):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No sessions" in result.output


# ---------------------------------------------------------------------------
# session new
# ---------------------------------------------------------------------------


class TestSessionNewCommand:
    def test_new_uses_runtime_defaults_when_flags_missing(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        created = _make_session("new-id", "default")
        svc = MagicMock()
        svc.create_session = AsyncMock(return_value=created)
        svc.list_frameworks = MagicMock(return_value=["direct"])
        svc.list_models = MagicMock(
            return_value=[MagicMock(model_id="gemma4-26b-local")]
        )

        import contextlib

        @contextlib.asynccontextmanager
        async def _ctx():
            yield svc

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", _ctx):
            result = runner.invoke(app, ["new"])

        assert result.exit_code == 0
        cfg = svc.create_session.call_args[0][0]
        assert cfg.framework == "direct"
        assert cfg.default_model_id == "gemma4-26b-local"

    def test_new_honours_explicit_flags(self) -> None:
        from citnega.apps.cli.commands.session import app

        runner = CliRunner()
        created = _make_session("new-id", "explicit")
        svc = MagicMock()
        svc.create_session = AsyncMock(return_value=created)
        svc.list_frameworks = MagicMock(return_value=["direct"])
        svc.list_models = MagicMock(return_value=[MagicMock(model_id="gemma4-26b-local")])

        import contextlib

        @contextlib.asynccontextmanager
        async def _ctx():
            yield svc

        with patch("citnega.apps.cli.commands.session.cli_bootstrap", _ctx):
            result = runner.invoke(
                app,
                ["new", "--framework", "adk", "--model", "gpt-4o"],
            )

        assert result.exit_code == 0
        cfg = svc.create_session.call_args[0][0]
        assert cfg.framework == "adk"
        assert cfg.default_model_id == "gpt-4o"
