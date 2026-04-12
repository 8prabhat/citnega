"""
Stub adapter LSP suite.

The StubFrameworkAdapter (used in Phase 2 integration tests) must also
pass the shared LSP suite — it is the reference implementation.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

import pytest

from tests.adapters.shared_suite import AdapterLSPBase
from tests.fixtures.stub_adapter import StubFrameworkAdapter

if TYPE_CHECKING:
    from pathlib import Path


class TestStubAdapterLSP(AdapterLSPBase):
    """Stub adapter must pass every LSP assertion."""

    def _make_adapter(self, tmp_path: Path) -> StubFrameworkAdapter:
        return StubFrameworkAdapter()

    # Override: stub runner.run_turn needs a queue — test separately
    @pytest.mark.asyncio
    async def test_run_turn_completes(self, tmp_path: Path) -> None:
        import asyncio
        from datetime import datetime
        import uuid

        from citnega.packages.protocol.models.context import ContextObject

        adapter = self._make_adapter(tmp_path)
        session = self._session_helper(adapter.framework_name)
        runner = await adapter.create_runner(session, [], None)

        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        ctx = ContextObject(
            session_id=session.config.session_id,
            run_id=str(uuid.uuid4()),
            user_input="hello",
            assembled_at=datetime.now(tz=UTC),
            budget_remaining=4096,
        )
        run_id = await runner.run_turn("hello", ctx, queue)
        assert run_id == ctx.run_id

    def _session_helper(self, framework: str):  # type: ignore[return]
        from datetime import datetime

        from citnega.packages.protocol.models.sessions import Session, SessionConfig

        cfg = SessionConfig(
            session_id="stub-test",
            name="stub",
            framework=framework,
            default_model_id="x",
        )
        now = datetime.now(tz=UTC)
        return Session(config=cfg, created_at=now, last_active_at=now)
