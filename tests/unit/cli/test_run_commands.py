"""
FR-UX-002 — CLI run controls parity tests.

Tests: run (stream, Ctrl+C cancel), run cancel subcommand.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from citnega.apps.cli.commands.run import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "sess-1"):
    from datetime import UTC, datetime

    from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState

    cfg = SessionConfig(
        session_id=session_id,
        name="test",
        framework="adk",
        default_model_id="m",
    )
    return Session(
        config=cfg,
        created_at=datetime.now(tz=UTC),
        last_active_at=datetime.now(tz=UTC),
        state=SessionState.IDLE,
        run_count=0,
    )


class _FakeEvent:
    """Minimal event stub."""

    def __init__(self, event_type: str = "SomeEvent", **kw):
        self._type = event_type
        self.__dict__.update(kw)

    def model_dump(self):
        return {"event_type": self._type}


def _make_service(session=None, events=None, run_id="run-abc"):
    svc = MagicMock()
    svc.get_session = AsyncMock(return_value=session if session is not None else _make_session())
    svc.run_turn = AsyncMock(return_value=run_id)
    svc.cancel_run = AsyncMock()

    async def _stream(rid):
        for ev in (events or []):
            yield ev

    svc.stream_events = _stream
    return svc


def _bootstrap_ctx(svc):
    @contextlib.asynccontextmanager
    async def _ctx():
        yield svc

    return _ctx


# ---------------------------------------------------------------------------
# run command — normal flow
# ---------------------------------------------------------------------------


def _complete_event(final_state=None):
    from citnega.packages.protocol.events.lifecycle import RunCompleteEvent
    from citnega.packages.protocol.models.runs import RunState

    return RunCompleteEvent(
        session_id="sess-1",
        run_id="run-abc",
        final_state=final_state or RunState.COMPLETED,
    )


class TestRunCommand:
    def test_run_basic_completes(self) -> None:
        events = [_complete_event()]
        svc = _make_service(events=events)

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["run", "--session", "sess-1", "--prompt", "hello"])

        assert result.exit_code == 0

    def test_run_session_not_found_exits_nonzero(self) -> None:
        svc = _make_service()
        svc.get_session = AsyncMock(return_value=None)

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["run", "--session", "no-such", "--prompt", "hi"])

        assert result.exit_code != 0

    def test_run_failed_state_exits_nonzero(self) -> None:
        from citnega.packages.protocol.models.runs import RunState

        events = [_complete_event(RunState.FAILED)]
        svc = _make_service(events=events)

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["run", "--session", "sess-1", "--prompt", "boom"])

        assert result.exit_code != 0

    def test_run_quiet_suppresses_output(self) -> None:
        events = [_complete_event()]
        svc = _make_service(events=events)

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(
                app, ["run", "--session", "sess-1", "--prompt", "hi", "--quiet"]
            )

        # run_id should not be printed in quiet mode
        assert "run-abc" not in result.output
        assert result.exit_code == 0

    def test_run_json_emits_json_lines(self) -> None:
        import json

        events = [_complete_event()]
        svc = _make_service(events=events)

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(
                app, ["run", "--session", "sess-1", "--prompt", "hi", "--json"]
            )

        # Lines starting with '{' should be valid JSON (stderr lines are mixed in)
        json_lines = [ln for ln in result.output.strip().splitlines() if ln.startswith("{")]
        assert len(json_lines) >= 1
        for line in json_lines:
            json.loads(line)  # raises if invalid

    def test_run_calls_run_turn_with_prompt(self) -> None:
        svc = _make_service(events=[])

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            runner.invoke(app, ["run", "--session", "sess-1", "--prompt", "my-prompt"])

        svc.run_turn.assert_called_once_with("sess-1", "my-prompt")


# ---------------------------------------------------------------------------
# run — Ctrl+C / cancellation
# ---------------------------------------------------------------------------


class TestRunCancellation:
    def test_keyboard_interrupt_cancels_run(self) -> None:
        """When KeyboardInterrupt fires during streaming, cancel_run is called."""

        async def _stream_raise(rid):
            raise KeyboardInterrupt
            yield  # make it an async generator

        svc = _make_service()
        svc.stream_events = _stream_raise

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["run", "--session", "sess-1", "--prompt", "hi"])

        svc.cancel_run.assert_called_once()
        assert result.exit_code == 130

    def test_keyboard_interrupt_cancel_failure_still_exits_130(self) -> None:
        """Even if cancel_run raises, exit code is 130."""

        async def _stream_raise(rid):
            raise KeyboardInterrupt
            yield

        svc = _make_service()
        svc.stream_events = _stream_raise
        svc.cancel_run = AsyncMock(side_effect=RuntimeError("cancel failed"))

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["run", "--session", "sess-1", "--prompt", "hi"])

        assert result.exit_code == 130


# ---------------------------------------------------------------------------
# run cancel subcommand
# ---------------------------------------------------------------------------


class TestRunCancelCommand:
    def test_cancel_calls_service(self) -> None:
        svc = MagicMock()
        svc.cancel_run = AsyncMock()

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["cancel", "--run-id", "run-xyz"])

        svc.cancel_run.assert_called_once_with("run-xyz")
        assert result.exit_code == 0

    def test_cancel_failure_exits_nonzero(self) -> None:
        svc = MagicMock()
        svc.cancel_run = AsyncMock(side_effect=RuntimeError("not found"))

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["cancel", "--run-id", "run-xyz"])

        assert result.exit_code != 0

    def test_cancel_prints_confirmation(self) -> None:
        svc = MagicMock()
        svc.cancel_run = AsyncMock()

        runner = CliRunner()
        with patch("citnega.apps.cli.commands.run.cli_bootstrap", _bootstrap_ctx(svc)):
            result = runner.invoke(app, ["cancel", "--run-id", "run-xyz"])

        assert "run-xyz" in result.output
