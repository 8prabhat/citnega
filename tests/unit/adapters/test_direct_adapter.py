"""Unit tests for DirectModelAdapter default model resolution."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from citnega.packages.adapters.direct.adapter import DirectModelAdapter
from citnega.packages.protocol.interfaces.adapter import AdapterConfig
from citnega.packages.protocol.models.sessions import Session, SessionConfig


def _make_session(session_id: str, model_id: str) -> Session:
    cfg = SessionConfig(
        session_id=session_id,
        name="direct-session",
        framework="direct",
        default_model_id=model_id,
    )
    now = datetime.now(tz=UTC)
    return Session(config=cfg, created_at=now, last_active_at=now)


@pytest.mark.asyncio
async def test_session_default_model_takes_precedence(tmp_path) -> None:
    adapter = DirectModelAdapter(sessions_dir=tmp_path)
    await adapter.initialize(
        AdapterConfig(framework_name="direct", default_model_id="gemma4-12b-local")
    )

    session = _make_session("s1", "gpt-4o")
    runner = await adapter.create_runner(session, callables=[], model_gateway=None)

    assert runner._conv.active_model_id == "gpt-4o"


@pytest.mark.asyncio
async def test_config_default_model_used_when_session_model_missing(tmp_path) -> None:
    adapter = DirectModelAdapter(sessions_dir=tmp_path)
    await adapter.initialize(
        AdapterConfig(framework_name="direct", default_model_id="gemma4-12b-local")
    )

    session = _make_session("s2", "")
    runner = await adapter.create_runner(session, callables=[], model_gateway=None)

    assert runner._conv.active_model_id == "gemma4-12b-local"
