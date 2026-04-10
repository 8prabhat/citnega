"""
Integration tests for the Phase 9 composition root and shutdown handler.

Strategy:
  - ``create_application()`` is tested with skip_provider_health_check=True
    and framework="stub" so no live model server or framework SDK is needed.
  - Exit-code tests use subprocess.run() so SystemExit propagates cleanly
    without contaminating the test process.
  - ShutdownCoordinator is tested by wiring it to a real (but lightweight)
    in-process service and simulating a signal.
  - Replay harness tests cover event log loading, state reconstruction, and
    the diff logic against a mocked DB record.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from citnega.packages.bootstrap.bootstrap import (
    EXIT_ADAPTER_ERROR,
    EXIT_CONFIG_ERROR,
    EXIT_MIGRATION_ERROR,
    EXIT_NO_PROVIDER,
    create_application,
)
from citnega.packages.protocol.models.sessions import SessionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TestCreateApplication — happy path
# ---------------------------------------------------------------------------

class TestCreateApplication:
    """create_application() boots a real service backed by SQLite."""

    def test_yields_application_service(self, tmp_path: Path) -> None:
        from citnega.packages.runtime.app_service import ApplicationService

        async def _do():
            async with create_application(
                db_path=tmp_path / "test.db",
                framework="stub",
                run_migrations=False,
                skip_provider_health_check=True,
            ) as svc:
                assert isinstance(svc, ApplicationService)

        _run(_do())

    def test_can_create_and_list_sessions(self, tmp_path: Path) -> None:
        async def _do():
            async with create_application(
                db_path=tmp_path / "test.db",
                framework="stub",
                run_migrations=True,
                skip_provider_health_check=True,
            ) as svc:
                cfg = SessionConfig(
                    session_id=str(uuid.uuid4()),
                    name="bootstrap-test",
                    framework="stub",
                    default_model_id="",
                )
                await svc.create_session(cfg)
                sessions = await svc.list_sessions()
                ids = [s.config.session_id for s in sessions]
                assert cfg.session_id in ids

        _run(_do())

    def test_can_run_a_turn(self, tmp_path: Path) -> None:
        async def _do():
            async with create_application(
                db_path=tmp_path / "test.db",
                framework="stub",
                run_migrations=True,
                skip_provider_health_check=True,
            ) as svc:
                cfg = SessionConfig(
                    session_id=str(uuid.uuid4()),
                    name="turn-test",
                    framework="stub",
                    default_model_id="",
                )
                await svc.create_session(cfg)
                run_id = await svc.run_turn(cfg.session_id, "hello world")
                assert run_id  # non-empty

        _run(_do())

    def test_db_file_created(self, tmp_path: Path) -> None:
        db_path = tmp_path / "check.db"

        async def _do():
            async with create_application(
                db_path=db_path,
                framework="stub",
                run_migrations=False,
                skip_provider_health_check=True,
            ) as svc:
                pass  # just bootstrap and shutdown

        _run(_do())
        assert db_path.exists()

    def test_shutdown_idempotent(self, tmp_path: Path) -> None:
        """shutdown() called twice should not raise."""
        async def _do():
            async with create_application(
                db_path=tmp_path / "idem.db",
                framework="stub",
                run_migrations=False,
                skip_provider_health_check=True,
            ) as svc:
                # Trigger shutdown manually; the context manager exit also calls it
                await svc._runtime.shutdown()

        # Should not raise
        _run(_do())


# ---------------------------------------------------------------------------
# TestExitCodes — failure modes tested via subprocess
# ---------------------------------------------------------------------------

_HELPER_SCRIPT = """
import sys, asyncio
sys.path.insert(0, "{citnega_root}")

from citnega.packages.bootstrap.bootstrap import create_application

async def main():
    async with create_application(
        framework={framework!r},
        run_migrations=False,
        skip_provider_health_check={skip_health!r},
    ) as svc:
        pass

asyncio.run(main())
"""


class TestExitCodes:
    def _run_subprocess(self, script: str, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )

    def test_unknown_framework_exits_3(self, tmp_path: Path) -> None:
        """An unknown framework name must exit with code EXIT_ADAPTER_ERROR (3)."""
        root = Path(__file__).parents[3]
        script = _HELPER_SCRIPT.format(
            citnega_root=str(root),
            framework="not_a_real_framework",
            skip_health=True,
        )
        result = self._run_subprocess(script, tmp_path)
        assert result.returncode == EXIT_ADAPTER_ERROR, (
            f"Expected exit {EXIT_ADAPTER_ERROR}, got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestShutdownCoordinator
# ---------------------------------------------------------------------------

class TestShutdownCoordinator:
    def _make_service(self, tmp_path: Path):
        """Create a minimal ApplicationService for shutdown tests."""
        import aiosqlite  # noqa: F401 (ensure available)

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
        from citnega.packages.protocol.interfaces.context import IContextHandler
        from citnega.packages.protocol.models.context import ContextObject
        from citnega.packages.protocol.models.sessions import Session
        from tests.fixtures.stub_adapter import StubFrameworkAdapter

        db_path = tmp_path / "shutdown_test.db"

        async def _setup():
            db = DatabaseFactory(db_path)
            await db.connect()
            ddl_statements = [
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    framework TEXT NOT NULL, default_model_id TEXT NOT NULL DEFAULT '',
                    local_only INTEGER NOT NULL DEFAULT 1,
                    max_callable_depth INTEGER NOT NULL DEFAULT 2,
                    kb_enabled INTEGER NOT NULL DEFAULT 0,
                    max_context_tokens INTEGER NOT NULL DEFAULT 8192,
                    approval_timeout_seconds INTEGER NOT NULL DEFAULT 300,
                    tags TEXT NOT NULL DEFAULT '[]',
                    config_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'idle',
                    created_at TEXT NOT NULL, last_active_at TEXT NOT NULL,
                    run_count INTEGER NOT NULL DEFAULT 0
                )""",
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    started_at TEXT NOT NULL, finished_at TEXT,
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0, error_message TEXT
                )""",
            ]
            for ddl in ddl_statements:
                async with db.write_lock:
                    await db.execute(ddl)

            session_repo = SessionRepository(db)
            run_repo     = RunRepository(db)
            session_mgr  = SessionManager(session_repo)
            run_mgr      = RunManager(run_repo)
            emitter      = EventEmitter()
            approval_mgr = ApprovalManager()
            enforcer     = PolicyEnforcer(emitter, approval_mgr)
            adapter      = StubFrameworkAdapter()
            registry     = BaseRegistry()

            class _PT(IContextHandler):
                @property
                def name(self) -> str:
                    return "pass_through"
                async def enrich(self, ctx: ContextObject, s: Session) -> ContextObject:
                    return ctx

            assembler = ContextAssembler([_PT()])
            runtime   = CoreRuntime(
                session_manager=session_mgr,
                run_manager=run_mgr,
                context_assembler=assembler,
                framework_adapter=adapter,
                event_emitter=emitter,
                callable_registry=registry,
            )
            svc = ApplicationService(
                runtime=runtime,
                emitter=emitter,
                approval_manager=approval_mgr,
            )
            return svc, runtime, emitter, db

        return asyncio.run(_setup())

    def test_shutdown_completes(self, tmp_path: Path) -> None:
        from citnega.packages.bootstrap.shutdown import ShutdownCoordinator

        svc, runtime, emitter, db = self._make_service(tmp_path)

        async def _do():
            coord = ShutdownCoordinator(runtime, emitter, db)
            await coord.shutdown()
            assert coord.shutdown_requested

        asyncio.run(_do())

    def test_shutdown_idempotent(self, tmp_path: Path) -> None:
        from citnega.packages.bootstrap.shutdown import ShutdownCoordinator

        svc, runtime, emitter, db = self._make_service(tmp_path)

        async def _do():
            coord = ShutdownCoordinator(runtime, emitter, db)
            await coord.shutdown()
            await coord.shutdown()  # second call should be no-op

        asyncio.run(_do())

    def test_wait_for_shutdown(self, tmp_path: Path) -> None:
        from citnega.packages.bootstrap.shutdown import ShutdownCoordinator

        svc, runtime, emitter, db = self._make_service(tmp_path)

        async def _do():
            coord = ShutdownCoordinator(runtime, emitter, db)

            async def _trigger():
                await asyncio.sleep(0.05)
                await coord.shutdown()

            asyncio.create_task(_trigger())
            await asyncio.wait_for(coord.wait_for_shutdown(), timeout=2.0)
            assert coord.shutdown_requested

        asyncio.run(_do())


# ---------------------------------------------------------------------------
# TestReplay — event log replay harness
# ---------------------------------------------------------------------------

class TestReplay:
    def _write_events(self, path: Path, events: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")

    def _sample_events(self, run_id: str, session_id: str) -> list[dict]:
        now = datetime.now(tz=timezone.utc).isoformat()
        return [
            {
                "event_type": "run_state",
                "event_id": str(uuid.uuid4()),
                "run_id": run_id,
                "session_id": session_id,
                "ts": now,
                "new_state": "executing",
            },
            {
                "event_type": "callable_start",
                "event_id": "call-1",
                "run_id": run_id,
                "session_id": session_id,
                "ts": now,
                "callable_name": "fetch_url",
            },
            {
                "event_type": "callable_end",
                "event_id": "call-1",
                "run_id": run_id,
                "session_id": session_id,
                "ts": now,
                "error_code": None,
            },
            {
                "event_type": "run_complete",
                "event_id": str(uuid.uuid4()),
                "run_id": run_id,
                "session_id": session_id,
                "ts": now,
                "final_state": "completed",
                "total_tokens": 512,
                "turn_count": 1,
            },
        ]

    def test_load_event_log(self, tmp_path: Path) -> None:
        from scripts.replay import load_event_log

        run_id = str(uuid.uuid4())
        path = tmp_path / f"{run_id}.jsonl"
        events = self._sample_events(run_id, "sess-1")
        self._write_events(path, events)

        loaded = load_event_log(path)
        assert len(loaded) == 4

    def test_replayed_state_final(self, tmp_path: Path) -> None:
        from scripts.replay import ReplayedState, load_event_log

        run_id = str(uuid.uuid4())
        path = tmp_path / f"{run_id}.jsonl"
        events = self._sample_events(run_id, "sess-1")
        self._write_events(path, events)

        raw = load_event_log(path)
        replayed = ReplayedState(run_id=run_id)
        for ev in raw:
            replayed.apply(ev)

        assert replayed.state == "completed"
        assert replayed.session_id == "sess-1"
        assert replayed.total_tokens == 512
        assert replayed.turn_count == 1

    def test_callable_invocations_tracked(self, tmp_path: Path) -> None:
        from scripts.replay import ReplayedState, load_event_log

        run_id = str(uuid.uuid4())
        path = tmp_path / f"{run_id}.jsonl"
        self._write_events(path, self._sample_events(run_id, "sess-1"))

        raw = load_event_log(path)
        replayed = ReplayedState(run_id=run_id)
        for ev in raw:
            replayed.apply(ev)

        assert len(replayed.callable_invocations) == 1
        assert replayed.callable_invocations[0]["callable_name"] == "fetch_url"
        assert replayed.callable_invocations[0]["success"] is True

    def test_no_divergence_matching_state(self, tmp_path: Path) -> None:
        from scripts.replay import ReplayedState, diff_states

        run_id = str(uuid.uuid4())
        replayed = ReplayedState(
            run_id=run_id,
            session_id="sess-x",
            state="completed",
        )
        db_record = {"run_id": run_id, "session_id": "sess-x", "state": "completed"}
        divergences = diff_states(replayed, db_record)
        assert divergences == []

    def test_divergence_state_mismatch(self, tmp_path: Path) -> None:
        from scripts.replay import ReplayedState, diff_states

        run_id = str(uuid.uuid4())
        replayed = ReplayedState(
            run_id=run_id,
            session_id="sess-x",
            state="completed",
        )
        db_record = {"run_id": run_id, "session_id": "sess-x", "state": "failed"}
        divergences = diff_states(replayed, db_record)
        assert any("state" in d for d in divergences)

    def test_skips_invalid_json_lines(self, tmp_path: Path) -> None:
        from scripts.replay import load_event_log

        run_id = str(uuid.uuid4())
        path = tmp_path / f"{run_id}.jsonl"
        with path.open("w") as fh:
            fh.write('{"event_type": "run_state", "run_id": "x"}\n')
            fh.write("NOT JSON\n")
            fh.write('{"event_type": "run_complete", "run_id": "x"}\n')

        loaded = load_event_log(path)
        assert len(loaded) == 2  # bad line skipped

    def test_main_exit_0_no_db(self, tmp_path: Path) -> None:
        """CLI main exits 0 when event log exists but no DB to compare against."""
        from scripts.replay import _main
        import argparse

        run_id = str(uuid.uuid4())
        event_log = tmp_path / f"{run_id}.jsonl"
        events = self._sample_events(run_id, "sess-1")
        self._write_events(event_log, events)

        args = argparse.Namespace(
            run_id=run_id,
            db=None,
            event_log=str(event_log),
            json=False,
        )
        exit_code = asyncio.run(_main(args))
        assert exit_code == 0

    def test_main_exit_1_missing_log(self, tmp_path: Path) -> None:
        """CLI main exits 1 when event log is not found."""
        from scripts.replay import _main
        import argparse

        args = argparse.Namespace(
            run_id="no-such-run-id",
            db=None,
            event_log=str(tmp_path / "no_such.jsonl"),
            json=False,
        )
        exit_code = asyncio.run(_main(args))
        assert exit_code == 1

    def test_main_json_output(self, tmp_path: Path) -> None:
        """JSON output mode produces valid JSON with expected keys."""
        from scripts.replay import _main
        import argparse
        import io
        from contextlib import redirect_stdout

        run_id = str(uuid.uuid4())
        event_log = tmp_path / f"{run_id}.jsonl"
        self._write_events(event_log, self._sample_events(run_id, "sess-1"))

        args = argparse.Namespace(
            run_id=run_id,
            db=None,
            event_log=str(event_log),
            json=True,
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = asyncio.run(_main(args))

        data = json.loads(buf.getvalue())
        assert data["run_id"] == run_id
        assert data["replayed_state"] == "completed"
        assert data["event_count"] == 4
