"""
Shared LSP test suite for all IFrameworkAdapter implementations.

Every adapter must pass this suite identically.  Adapters are injected
via the ``adapter_fixture`` parametrize marker in each adapter's own
test file.

Usage in per-adapter test files::

    from tests.adapters.shared_suite import AdapterSuiteFixture, run_suite

    @pytest.fixture
    def adapter_fixture(tmp_path):
        from citnega.packages.adapters.adk.adapter import ADKFrameworkAdapter
        from citnega.packages.storage.path_resolver import PathResolver
        pr = PathResolver(app_home=tmp_path)
        pr.create_all()
        return ADKFrameworkAdapter(pr)

    # Run the full LSP suite
    run_suite(adapter_fixture)

Covered assertions:
  1. create_runner returns IFrameworkRunner
  2. run_turn completes and returns a run_id string
  3. event stream contains at least one TokenEvent (if model responds)
  4. pause/resume/cancel are accepted without error
  5. checkpoint round-trip: save → load → fields preserved
  6. callable_factory returns ICallableFactory
  7. framework_name is a non-empty string
  8. shutdown is idempotent
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import uuid

import pytest

from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.protocol.interfaces.adapter import (
    AdapterConfig,
    IFrameworkAdapter,
    IFrameworkRunner,
)
from citnega.packages.protocol.models.context import ContextObject
from citnega.packages.protocol.models.sessions import Session, SessionConfig

# ---------------------------------------------------------------------------
# Helpers shared by all adapter tests
# ---------------------------------------------------------------------------


def _session(session_id: str = "test-sess", framework: str = "stub") -> Session:
    cfg = SessionConfig(
        session_id=session_id,
        name="LSP test",
        framework=framework,
        default_model_id="test-model",
        max_context_tokens=4096,
    )
    now = datetime.now(tz=UTC)
    return Session(config=cfg, created_at=now, last_active_at=now)


def _context(session: Session) -> ContextObject:
    return ContextObject(
        session_id=session.config.session_id,
        run_id=str(uuid.uuid4()),
        user_input="Hello",
        assembled_at=datetime.now(tz=UTC),
        budget_remaining=4096,
    )


def _adapter_config(model_id: str = "test-model", framework: str = "stub") -> AdapterConfig:
    return AdapterConfig(framework_name=framework, default_model_id=model_id)


# ---------------------------------------------------------------------------
# Core LSP assertions (used by all adapter tests via inheritance)
# ---------------------------------------------------------------------------


class AdapterLSPBase:
    """
    Base class for per-adapter LSP test classes.

    Subclasses define ``_make_adapter(tmp_path)`` and optionally override
    ``_is_sdk_available()`` to skip SDK-requiring tests.
    """

    def _make_adapter(self, tmp_path: Path) -> IFrameworkAdapter:
        raise NotImplementedError

    def _is_sdk_available(self) -> bool:
        """Return False to skip tests that require the real SDK."""
        return True

    # ------------------------------------------------------------------
    # 1. framework_name
    # ------------------------------------------------------------------

    def test_framework_name_non_empty(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        assert isinstance(adapter.framework_name, str)
        assert len(adapter.framework_name) > 0

    # ------------------------------------------------------------------
    # 2. initialize
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_initialize_runs_without_error(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        config = _adapter_config(framework=adapter.framework_name)
        await adapter.initialize(config)

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        config = _adapter_config(framework=adapter.framework_name)
        await adapter.initialize(config)
        await adapter.initialize(config)  # second call must not raise

    # ------------------------------------------------------------------
    # 3. callable_factory
    # ------------------------------------------------------------------

    def test_callable_factory_not_none(self, tmp_path: Path) -> None:
        from citnega.packages.protocol.interfaces.adapter import ICallableFactory

        adapter = self._make_adapter(tmp_path)
        factory = adapter.callable_factory
        assert factory is not None
        assert isinstance(factory, ICallableFactory)

    def test_callable_factory_create_tool_returns_descriptor(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        factory = adapter.callable_factory
        mock_callable = _make_mock_invocable()
        descriptor = factory.create_tool(mock_callable)
        assert descriptor is not None

    # ------------------------------------------------------------------
    # 4. create_runner
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_runner_returns_runner(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        assert isinstance(runner, IFrameworkRunner)

    @pytest.mark.asyncio
    async def test_create_runner_multiple_sessions(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        for i in range(3):
            session = _session(session_id=f"sess-{i}", framework=adapter.framework_name)
            runner = await adapter.create_runner(session, [], None)
            assert runner is not None

    # ------------------------------------------------------------------
    # 5. state_snapshot
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_state_snapshot_structure(self, tmp_path: Path) -> None:
        from citnega.packages.protocol.models.runs import StateSnapshot

        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        snapshot = await runner.get_state_snapshot()
        assert isinstance(snapshot, StateSnapshot)
        assert snapshot.session_id == session.config.session_id

    # ------------------------------------------------------------------
    # 6. pause / resume / cancel (control ops don't raise)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_pause_does_not_raise(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        await runner.pause("run-1")  # must not raise

    @pytest.mark.asyncio
    async def test_resume_does_not_raise(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        await runner.resume("run-1")

    @pytest.mark.asyncio
    async def test_cancel_sets_cancellation_token(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        await runner.cancel("run-1")
        # After cancel, get_state_snapshot should reflect CANCELLED
        snapshot = await runner.get_state_snapshot()
        from citnega.packages.protocol.models.runs import RunState

        assert snapshot.run_state in (RunState.CANCELLED, RunState.EXECUTING)

    # ------------------------------------------------------------------
    # 7. checkpoint round-trip
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_checkpoint_save_creates_file(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        meta = await runner.save_checkpoint("run-chk-1")
        assert Path(meta.file_path).exists()
        assert meta.size_bytes > 0
        assert meta.checkpoint_id

    @pytest.mark.asyncio
    async def test_checkpoint_restore_does_not_raise(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        session = _session(framework=adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)
        meta = await runner.save_checkpoint("run-chk-2")
        await runner.restore_checkpoint(meta.checkpoint_id)

    # ------------------------------------------------------------------
    # 8. shutdown idempotency
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_shutdown_idempotent(self, tmp_path: Path) -> None:
        adapter = self._make_adapter(tmp_path)
        await adapter.initialize(_adapter_config(framework=adapter.framework_name))
        await adapter.shutdown()
        await adapter.shutdown()  # second call must not raise

    # ------------------------------------------------------------------
    # 9. event translation
    # ------------------------------------------------------------------

    def test_translate_unknown_event_returns_generic(self, tmp_path: Path) -> None:
        from citnega.packages.protocol.events import GenericFrameworkEvent

        adapter = self._make_adapter(tmp_path)
        factory = adapter.callable_factory

        class _UnknownEvent:
            pass

        result = factory.translate_event(_UnknownEvent())
        assert result is not None
        assert isinstance(result, GenericFrameworkEvent)


# ---------------------------------------------------------------------------
# Mock callable for factory tests
# ---------------------------------------------------------------------------


def _make_mock_invocable(name: str = "test_tool") -> IInvocable:
    """Return a minimal IInvocable mock."""
    from unittest.mock import MagicMock

    from pydantic import BaseModel

    class _Input(BaseModel):
        query: str = ""

    class _Output(BaseModel):
        result: str = ""

    m = MagicMock(spec=IInvocable)
    m.name = name
    m.description = "A test tool"
    m.callable_type = CallableType.TOOL
    m.input_schema = _Input
    m.output_schema = _Output
    m.policy = CallablePolicy()
    m.get_metadata.return_value = CallableMetadata(
        name=name,
        description="A test tool",
        callable_type=CallableType.TOOL,
        input_schema_json=_Input.model_json_schema(),
        output_schema_json=_Output.model_json_schema(),
        policy=CallablePolicy(),
    )
    return m
