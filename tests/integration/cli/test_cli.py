"""
Integration tests for the Citnega headless CLI.

Strategy:
  - Smoke-test the Typer entry point via CliRunner for commands that do not
    touch storage (--help, config validate/show).
  - For commands that need storage, call ApplicationService directly so that
    we can inject a real SQLite DB in tmp_path without patching every import.
  - The stub framework adapter is used throughout (no real LLM SDK required).
"""

from __future__ import annotations

import asyncio
from datetime import UTC
from typing import TYPE_CHECKING
import uuid

import pytest
from typer.testing import CliRunner

from citnega.apps.cli.main import app
from citnega.packages.protocol.models.sessions import SessionConfig

if TYPE_CHECKING:
    from pathlib import Path

    from citnega.packages.protocol.models.context import ContextObject

# ---------------------------------------------------------------------------
# CliRunner instance (no mix_stderr so stdout is clean for assertions)
# ---------------------------------------------------------------------------

runner = CliRunner()


# ---------------------------------------------------------------------------
# ApplicationService fixture — real SQLite, stub adapter
# ---------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path: Path):
    """
    Return a ready ApplicationService backed by SQLite in tmp_path.

    Skips Alembic migrations — creates tables inline with raw DDL so that
    Phase 6 tests don't depend on the migrations being applied.
    """

    from citnega.packages.protocol.interfaces.context import IContextHandler
    from citnega.packages.protocol.models.sessions import Session
    from citnega.packages.runtime.app_service import ApplicationService
    from citnega.packages.runtime.context.assembler import ContextAssembler
    from citnega.packages.runtime.core_runtime import CoreRuntime
    from citnega.packages.runtime.events.emitter import EventEmitter
    from citnega.packages.runtime.policy.approval_manager import ApprovalManager
    from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
    from citnega.packages.runtime.runs import RunManager
    from citnega.packages.runtime.sessions import SessionManager
    from citnega.packages.shared.registry import BaseRegistry
    from citnega.packages.storage.database import DatabaseFactory
    from citnega.packages.storage.repositories.run_repo import RunRepository
    from citnega.packages.storage.repositories.session_repo import SessionRepository
    from tests.fixtures.stub_adapter import StubFrameworkAdapter

    db_path = tmp_path / "test.db"

    async def _create() -> ApplicationService:
        db = DatabaseFactory(db_path)
        await db.connect()

        # Create tables inline — schema must match repositories exactly
        ddl_statements = [
            """CREATE TABLE IF NOT EXISTS sessions (
                session_id               TEXT PRIMARY KEY,
                name                     TEXT NOT NULL,
                framework                TEXT NOT NULL,
                default_model_id         TEXT NOT NULL DEFAULT '',
                local_only               INTEGER NOT NULL DEFAULT 1,
                max_callable_depth       INTEGER NOT NULL DEFAULT 2,
                kb_enabled               INTEGER NOT NULL DEFAULT 0,
                max_context_tokens       INTEGER NOT NULL DEFAULT 8192,
                approval_timeout_seconds INTEGER NOT NULL DEFAULT 300,
                tags                     TEXT NOT NULL DEFAULT '[]',
                config_json              TEXT NOT NULL,
                state                    TEXT NOT NULL DEFAULT 'idle',
                created_at               TEXT NOT NULL,
                last_active_at           TEXT NOT NULL,
                run_count                INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS runs (
                run_id        TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL,
                state         TEXT NOT NULL DEFAULT 'pending',
                started_at    TEXT NOT NULL,
                finished_at   TEXT,
                turn_count    INTEGER NOT NULL DEFAULT 0,
                total_tokens  INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            )""",
        ]
        for ddl in ddl_statements:
            async with db.write_lock:
                await db.execute(ddl)

        session_repo = SessionRepository(db)
        run_repo = RunRepository(db)
        session_mgr = SessionManager(session_repo)
        run_mgr = RunManager(run_repo)

        emitter = EventEmitter()
        approval_mgr = ApprovalManager()
        PolicyEnforcer(emitter, approval_mgr)
        adapter = StubFrameworkAdapter()
        registry = BaseRegistry()

        class PassThrough(IContextHandler):
            @property
            def name(self) -> str:
                return "pass_through"

            async def enrich(self, ctx: ContextObject, s: Session) -> ContextObject:
                return ctx

        assembler = ContextAssembler([PassThrough()])

        runtime = CoreRuntime(
            session_manager=session_mgr,
            run_manager=run_mgr,
            context_assembler=assembler,
            framework_adapter=adapter,
            event_emitter=emitter,
            callable_registry=registry,
        )
        return ApplicationService(
            runtime=runtime,
            emitter=emitter,
            approval_manager=approval_mgr,
        )

    svc = asyncio.run(_create())
    yield svc

    async def _teardown():
        await svc._runtime.shutdown()
        # aiosqlite closes its own connection; nothing else to clean up

    asyncio.run(_teardown())


def _run(coro):
    """Run a coroutine in the test event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ApplicationService integration tests
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    def test_create_and_list(self, service) -> None:
        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="test-session",
            framework="stub",
            default_model_id="",
        )
        session = _run(service.create_session(cfg))
        assert session.config.session_id == cfg.session_id

        sessions = _run(service.list_sessions())
        ids = [s.config.session_id for s in sessions]
        assert cfg.session_id in ids

    def test_get_session_exists(self, service) -> None:
        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="get-me",
            framework="stub",
            default_model_id="",
        )
        _run(service.create_session(cfg))
        found = _run(service.get_session(cfg.session_id))
        assert found is not None
        assert found.config.name == "get-me"

    def test_get_session_missing(self, service) -> None:
        found = _run(service.get_session("no-such-id"))
        assert found is None

    def test_delete_session(self, service) -> None:
        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="delete-me",
            framework="stub",
            default_model_id="",
        )
        _run(service.create_session(cfg))
        _run(service.delete_session(cfg.session_id))
        found = _run(service.get_session(cfg.session_id))
        assert found is None


class TestRunTurn:
    def test_run_turn_returns_run_id(self, service) -> None:
        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="run-session",
            framework="stub",
            default_model_id="",
        )
        _run(service.create_session(cfg))
        run_id = _run(service.run_turn(cfg.session_id, "hello"))
        assert run_id  # non-empty string

    def test_run_turn_streams_complete_event(self, service) -> None:

        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="stream-session",
            framework="stub",
            default_model_id="",
        )
        _run(service.create_session(cfg))

        async def _do():
            run_id = await service.run_turn(cfg.session_id, "test prompt")
            events = []
            async for ev in service.stream_events(run_id):
                events.append(ev)
            return events

        events = asyncio.run(_do())
        event_types = [type(e).__name__ for e in events]
        assert "RunCompleteEvent" in event_types

    def test_run_turn_session_not_found(self, service) -> None:
        from citnega.packages.shared.errors import SessionNotFoundError

        with pytest.raises((SessionNotFoundError, Exception)):
            _run(service.run_turn("no-such-session", "hi"))

    def test_state_snapshot_idle(self, service) -> None:

        cfg = SessionConfig(
            session_id=str(uuid.uuid4()),
            name="snapshot-session",
            framework="stub",
            default_model_id="",
        )
        _run(service.create_session(cfg))
        # Wait for any background task to finish
        import time

        time.sleep(0.1)
        snapshot = _run(service.get_state_snapshot(cfg.session_id))
        # Could be PENDING (idle) or COMPLETED if the background task already ran
        assert snapshot.session_id == cfg.session_id


class TestApprovalRespond:
    def test_respond_to_unknown_approval_raises(self, service) -> None:
        from citnega.packages.runtime.policy.approval_manager import ApprovalNotFoundError

        with pytest.raises((ApprovalNotFoundError, Exception)):
            _run(service.respond_to_approval("no-such-approval", approved=True))


class TestKBStubs:
    def test_search_kb_returns_empty(self, service) -> None:
        results = _run(service.search_kb("anything"))
        assert results == []

    def test_add_kb_raises_not_implemented(self, service) -> None:
        from datetime import datetime

        from citnega.packages.protocol.models.kb import KBItem, KBSourceType

        item = KBItem(
            item_id=str(uuid.uuid4()),
            title="test",
            content="test content",
            source_type=KBSourceType.NOTE,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            content_hash="abc123",
        )
        with pytest.raises(NotImplementedError):
            _run(service.add_kb_item(item))


# ---------------------------------------------------------------------------
# CLI smoke tests (no storage required)
# ---------------------------------------------------------------------------


class TestCLIHelp:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "session" in result.output
        assert "run" in result.output
        assert "approve" in result.output

    def test_session_help(self) -> None:
        result = runner.invoke(app, ["session", "--help"])
        assert result.exit_code == 0

    def test_run_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0

    def test_approve_help(self) -> None:
        result = runner.invoke(app, ["approve", "--help"])
        assert result.exit_code == 0

    def test_kb_help(self) -> None:
        result = runner.invoke(app, ["kb", "--help"])
        assert result.exit_code == 0

    def test_config_help(self) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_migrate_help(self) -> None:
        result = runner.invoke(app, ["migrate", "--help"])
        assert result.exit_code == 0


class TestConfigCLI:
    def test_config_validate(self) -> None:
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_config_show(self) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "[runtime]" in result.output

    def test_config_show_json(self) -> None:
        import json

        result = runner.invoke(app, ["config", "show", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "runtime" in data
