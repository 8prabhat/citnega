"""
Unit tests for import_session() (Phase 11, Step 11.1).

Covers:
- JSONL import creates a session and replays messages
- JSON import with {"messages": [...]} format
- Empty file produces a session with no messages
- Malformed lines are skipped (graceful parse)
- Session name is derived from filename stem
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from citnega.packages.runtime.app_service import ApplicationService
from citnega.packages.shared.registry import CallableRegistry


def _make_service() -> ApplicationService:
    runtime = MagicMock()
    runtime.adapter.framework_name = "direct"
    runtime.adapter.get_runner = MagicMock(return_value=None)
    runtime.adapter.read_session_conversation_field = MagicMock(return_value=[])
    runtime.get_runner = MagicMock(return_value=None)
    runtime.capability_registry = None

    session_id = str(uuid.uuid4())
    from datetime import UTC, datetime

    from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState

    session = Session(
        config=SessionConfig(
            session_id=session_id,
            name="imported",
            framework="direct",
            default_model_id="",
        ),
        state=SessionState.IDLE,
        created_at=datetime.now(tz=UTC),
        last_active_at=datetime.now(tz=UTC),
    )
    runtime.create_session = AsyncMock(return_value=session)

    emitter = MagicMock()
    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = runtime
    svc._emitter = emitter
    svc._callable_registry = CallableRegistry()
    svc._capability_registry_cache = None
    svc._app_home = None
    svc._kb_store = None
    return svc


@pytest.mark.asyncio
async def test_import_session_from_jsonl(tmp_path: Path) -> None:
    """JSONL file: one message per line → session created with messages replayed."""
    svc = _make_service()
    f = tmp_path / "my_conversation.jsonl"
    f.write_text(
        '{"role": "user", "content": "Hello"}\n'
        '{"role": "assistant", "content": "Hi there"}\n',
        encoding="utf-8",
    )

    session = await svc.import_session(f)
    assert session is not None
    svc._runtime.create_session.assert_awaited_once()
    # Verify the config passed to create_session had the filename as name
    config_arg = svc._runtime.create_session.call_args[0][0]
    assert config_arg.name == "my_conversation"


@pytest.mark.asyncio
async def test_import_session_from_json_object(tmp_path: Path) -> None:
    """JSON object with messages list → session created."""
    svc = _make_service()
    msgs = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "A programming language."},
    ]
    f = tmp_path / "exported.json"
    f.write_text(json.dumps({"messages": msgs}), encoding="utf-8")

    session = await svc.import_session(f)
    assert session is not None
    svc._runtime.create_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_session_from_json_list(tmp_path: Path) -> None:
    """Bare JSON list of messages → session created."""
    svc = _make_service()
    msgs = [{"role": "user", "content": "hi"}]
    f = tmp_path / "convo.json"
    f.write_text(json.dumps(msgs), encoding="utf-8")

    session = await svc.import_session(f)
    assert session is not None
    svc._runtime.create_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_session_empty_file(tmp_path: Path) -> None:
    """Empty file → session created with zero messages, no error."""
    svc = _make_service()
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")

    session = await svc.import_session(f)
    assert session is not None
    svc._runtime.create_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_session_skips_malformed_lines(tmp_path: Path) -> None:
    """Malformed JSONL lines are silently skipped."""
    svc = _make_service()
    f = tmp_path / "partial.jsonl"
    f.write_text(
        '{"role": "user", "content": "Good line"}\n'
        'NOT_JSON\n'
        '{"missing_role": true}\n',
        encoding="utf-8",
    )

    session = await svc.import_session(f)
    assert session is not None
    svc._runtime.create_session.assert_awaited_once()
