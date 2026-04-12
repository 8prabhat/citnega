"""
CrewAI adapter LSP suite.

SDK-requiring tests are skipped when crewai is not installed.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

import pytest

from tests.adapters.shared_suite import AdapterLSPBase

if TYPE_CHECKING:
    from pathlib import Path


class TestCrewAIAdapterLSP(AdapterLSPBase):
    """CrewAI adapter must pass every LSP assertion."""

    def _make_adapter(self, tmp_path: Path):  # type: ignore[return]
        from citnega.packages.adapters.crewai.adapter import CrewAIFrameworkAdapter
        from citnega.packages.storage.path_resolver import PathResolver

        pr = PathResolver(app_home=tmp_path)
        pr.create_all()
        return CrewAIFrameworkAdapter(pr)

    def _is_sdk_available(self) -> bool:
        import importlib.util

        return importlib.util.find_spec("crewai") is not None

    @pytest.mark.asyncio
    async def test_run_turn_raises_import_error_without_sdk(self, tmp_path: Path) -> None:
        """If crewai is not installed, run_turn must raise ImportError."""
        if self._is_sdk_available():
            pytest.skip("crewai is installed; ImportError test not applicable")

        import asyncio
        from datetime import datetime
        import uuid

        from citnega.packages.protocol.models.context import ContextObject

        adapter = self._make_adapter(tmp_path)
        from citnega.packages.protocol.models.sessions import Session, SessionConfig

        cfg = SessionConfig(
            session_id="crew-import-test",
            name="crew",
            framework="crewai",
            default_model_id="gpt-4",
        )
        now = datetime.now(tz=UTC)
        session = Session(config=cfg, created_at=now, last_active_at=now)
        runner = await adapter.create_runner(session, [], None)

        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        ctx = ContextObject(
            session_id=session.config.session_id,
            run_id=str(uuid.uuid4()),
            user_input="hi",
            assembled_at=now,
            budget_remaining=4096,
        )
        with pytest.raises(ImportError, match="crewai"):
            await runner.run_turn("hi", ctx, queue)
