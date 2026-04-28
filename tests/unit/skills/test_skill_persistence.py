"""
Unit tests for Batch 6 skill persistence and runner token improvements:
- SkillImprover writes .md file to disk
- _strip_thinking_blocks removes <think>...</think>
- _MODE_TOOL_EXCLUSIONS removes port_scanner in chat mode
- Rolling summary compaction (above threshold)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _strip_thinking_blocks ────────────────────────────────────────────────────

def test_thinking_strip_removes_think_blocks():
    from citnega.packages.adapters.direct.runner import _strip_thinking_blocks
    text = "Hello <think>this is reasoning</think> World"
    assert _strip_thinking_blocks(text) == "Hello  World"


def test_thinking_strip_multiline():
    from citnega.packages.adapters.direct.runner import _strip_thinking_blocks
    text = "Start\n<think>\nLine 1\nLine 2\n</think>\nEnd"
    result = _strip_thinking_blocks(text)
    assert "<think>" not in result
    assert "Start" in result
    assert "End" in result


def test_thinking_strip_no_ops_when_no_blocks():
    from citnega.packages.adapters.direct.runner import _strip_thinking_blocks
    text = "Just a normal response without any tags."
    assert _strip_thinking_blocks(text) == text


def test_thinking_strip_multiple_blocks():
    from citnega.packages.adapters.direct.runner import _strip_thinking_blocks
    text = "<think>first</think> middle <think>second</think> end"
    result = _strip_thinking_blocks(text)
    assert "first" not in result
    assert "second" not in result
    assert "middle" in result
    assert "end" in result


# ── _MODE_TOOL_EXCLUSIONS ──────────────────────────────────────────────────────

def test_mode_exclusions_chat_removes_port_scanner():
    from citnega.packages.adapters.direct.runner import _MODE_TOOL_EXCLUSIONS
    assert "port_scanner" in _MODE_TOOL_EXCLUSIONS["chat"]


def test_mode_exclusions_research_removes_run_shell():
    from citnega.packages.adapters.direct.runner import _MODE_TOOL_EXCLUSIONS
    assert "run_shell" in _MODE_TOOL_EXCLUSIONS["research"]


def test_mode_exclusions_code_removes_pivot_table():
    from citnega.packages.adapters.direct.runner import _MODE_TOOL_EXCLUSIONS
    assert "pivot_table" in _MODE_TOOL_EXCLUSIONS["code"]


# ── SkillImprover disk persistence ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_improver_writes_md_file(tmp_path: Path, monkeypatch):
    from citnega.packages.skills.improver import SkillImprover
    from citnega.packages.skills.impact_analyzer import SkillImpactScore

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    gateway = MagicMock()

    async def _fake_stream(req):
        class _Chunk:
            text = "Improved skill body content"
        yield _Chunk()

    gateway.stream_generate = _fake_stream

    with patch("citnega.packages.skills.builtins.BUILTIN_SKILL_INDEX", {
        "test_skill": {"name": "test_skill", "body": "Original body"}
    }):
        improver = SkillImprover(model_gateway=gateway, settings=None)
        improver._turn_counts["test_skill"] = 10

        score = MagicMock(spec=SkillImpactScore)
        score.skill_name = "test_skill"
        score.score = 0.9

        result = await improver.maybe_improve(score, "user input", "assistant reply")

    assert result is not None
    expected_path = tmp_path / ".citnega" / "skills" / "test_skill.md"
    assert expected_path.exists()
    assert "Improved" in expected_path.read_text()


# ── Rolling summary compaction ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rolling_summary_compacts_above_threshold(tmp_path):
    from citnega.packages.runtime.context.handlers.session_summary import SessionSummaryHandler

    run_repo = MagicMock()
    run_repo.list = AsyncMock(return_value=[])

    gateway = MagicMock()
    response = MagicMock()
    response.content = "This is a summary of the conversation."
    gateway.generate = AsyncMock(return_value=response)

    conv_store = MagicMock()
    # 25 messages — above threshold of 20
    messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(25)]
    conv_store.get_messages = MagicMock(return_value=messages)
    conv_store.compact = AsyncMock(return_value=10)

    session = MagicMock()
    session.config.session_id = "s1"
    session.config.name = "test"

    context = MagicMock()
    context.sources = []
    context.total_tokens = 0
    context.budget_remaining = 8000
    context.model_copy = MagicMock(return_value=context)

    handler = SessionSummaryHandler(
        run_repo,
        model_gateway=gateway,
        conversation_store=conv_store,
        summarize_threshold=20,
        summarize_window=15,
    )
    await handler.enrich(context, session)

    conv_store.compact.assert_called_once()
    call_args = conv_store.compact.call_args
    summary_msg = call_args[0][0] if call_args[0] else call_args.kwargs.get("summary", "")
    assert "[Summary of earlier conversation:" in summary_msg


@pytest.mark.asyncio
async def test_rolling_summary_idempotent_when_already_compacted():
    from citnega.packages.runtime.context.handlers.session_summary import SessionSummaryHandler

    run_repo = MagicMock()
    run_repo.list = AsyncMock(return_value=[])

    gateway = MagicMock()
    gateway.generate = AsyncMock()

    conv_store = MagicMock()
    messages = [
        {"role": "assistant", "content": "[Summary of earlier conversation: prior content]"},
        *[{"role": "user", "content": f"msg {i}"} for i in range(20)],
    ]
    conv_store.get_messages = MagicMock(return_value=messages)
    conv_store.compact = AsyncMock()

    session = MagicMock()
    session.config.session_id = "s1"
    session.config.name = "test"

    context = MagicMock()
    context.sources = []
    context.total_tokens = 0
    context.budget_remaining = 8000
    context.model_copy = MagicMock(return_value=context)

    handler = SessionSummaryHandler(
        run_repo,
        model_gateway=gateway,
        conversation_store=conv_store,
        summarize_threshold=20,
        summarize_window=15,
    )
    await handler.enrich(context, session)

    # Already compacted — compact should NOT be called again
    conv_store.compact.assert_not_called()
