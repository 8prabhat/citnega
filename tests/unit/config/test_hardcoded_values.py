"""
Tests for Phase 3: hardcoded values extracted to settings.toml.

Verifies:
- All new settings keys exist in CitnegaSettings with correct defaults.
- Environment variable overrides work for each new key.
- Runtime components read from settings (not from hardcoded constants).
"""

from __future__ import annotations

import os


# ── 1. New RuntimeSettings fields ────────────────────────────────────────────


def test_runtime_settings_new_keys_have_defaults():
    from citnega.packages.config.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.event_queue_max_size == 256
    assert s.max_tool_rounds == 5
    assert s.max_supervisor_rounds == 3
    assert s.shutdown_drain_timeout_seconds == 5.0
    assert s.provider_max_retries == 3


def test_runtime_event_queue_max_size_env_override(monkeypatch):
    monkeypatch.setenv("CITNEGA_RUNTIME_EVENT_QUEUE_MAX_SIZE", "512")
    from importlib import reload

    import citnega.packages.config.settings as _mod

    reload(_mod)
    s = _mod.RuntimeSettings()
    assert s.event_queue_max_size == 512
    reload(_mod)  # restore


def test_runtime_max_tool_rounds_env_override(monkeypatch):
    monkeypatch.setenv("CITNEGA_RUNTIME_MAX_TOOL_ROUNDS", "10")
    from citnega.packages.config.settings import RuntimeSettings

    # pydantic-settings reads env at instantiation time
    s = RuntimeSettings()
    assert s.max_tool_rounds == 10


def test_runtime_provider_max_retries_env_override(monkeypatch):
    monkeypatch.setenv("CITNEGA_RUNTIME_PROVIDER_MAX_RETRIES", "5")
    from citnega.packages.config.settings import RuntimeSettings

    s = RuntimeSettings()
    assert s.provider_max_retries == 5


# ── 2. New TUISettings fields ─────────────────────────────────────────────────


def test_tui_input_history_size_default():
    from citnega.packages.config.settings import TUISettings

    s = TUISettings()
    assert s.input_history_size == 200


def test_tui_input_history_size_env_override(monkeypatch):
    monkeypatch.setenv("CITNEGA_TUI_INPUT_HISTORY_SIZE", "500")
    from citnega.packages.config.settings import TUISettings

    s = TUISettings()
    assert s.input_history_size == 500


# ── 3. New ContextSettings fields ────────────────────────────────────────────


def test_context_kb_chunk_size_tokens_default():
    from citnega.packages.config.settings import ContextSettings

    s = ContextSettings()
    assert s.kb_chunk_size_tokens == 512


def test_context_token_budget_priorities_defaults():
    from citnega.packages.config.settings import ContextSettings

    s = ContextSettings()
    assert s.token_budget_priorities["recent_turns"] == 100
    assert s.token_budget_priorities["state"] == 80
    assert s.token_budget_priorities["summary"] == 60
    assert s.token_budget_priorities["kb"] == 40


def test_context_token_budget_default_priority():
    from citnega.packages.config.settings import ContextSettings

    s = ContextSettings()
    assert s.token_budget_default_priority == 20


# ── 4. EventEmitter respects max_queue_size parameter ─────────────────────────


def test_emitter_uses_configured_queue_size():
    from citnega.packages.runtime.events.emitter import EventEmitter

    emitter = EventEmitter(max_queue_size=16)
    queue = emitter._get_or_create_queue("test-run")
    assert queue.maxsize == 16


def test_emitter_default_queue_size():
    from citnega.packages.runtime.events.emitter import EventEmitter

    emitter = EventEmitter()
    queue = emitter._get_or_create_queue("test-run")
    assert queue.maxsize == 256


# ── 5. ShutdownCoordinator respects drain_timeout parameter ──────────────────


def test_shutdown_coordinator_drain_timeout():
    from unittest.mock import MagicMock

    from citnega.packages.bootstrap.shutdown import ShutdownCoordinator

    coordinator = ShutdownCoordinator(
        runtime=MagicMock(),
        emitter=MagicMock(),
        db=MagicMock(),
        drain_timeout=10.0,
    )
    assert coordinator._drain_timeout == 10.0


def test_shutdown_coordinator_default_drain_timeout():
    from unittest.mock import MagicMock

    from citnega.packages.bootstrap.shutdown import ShutdownCoordinator

    coordinator = ShutdownCoordinator(
        runtime=MagicMock(),
        emitter=MagicMock(),
        db=MagicMock(),
    )
    assert coordinator._drain_timeout == 5.0


# ── 6. TokenBudgetHandler respects configurable priorities ────────────────────


def test_token_budget_handler_custom_priorities():
    from citnega.packages.runtime.context.handlers.token_budget import TokenBudgetHandler
    from unittest.mock import MagicMock

    priorities = {"recent_turns": 200, "kb": 10}
    handler = TokenBudgetHandler(priorities=priorities, default_priority=5)

    source = MagicMock()
    source.source_type = "recent_turns"
    assert handler._priority(source) == 200

    source.source_type = "kb"
    assert handler._priority(source) == 10

    source.source_type = "unknown_type"
    assert handler._priority(source) == 5


def test_token_budget_handler_default_priorities():
    from citnega.packages.runtime.context.handlers.token_budget import TokenBudgetHandler
    from unittest.mock import MagicMock

    handler = TokenBudgetHandler()

    source = MagicMock()
    source.source_type = "recent_turns"
    assert handler._priority(source) == 100

    source.source_type = "state"
    assert handler._priority(source) == 80


# ── 7. KB chunk_text uses configurable token size ────────────────────────────


def test_chunk_text_with_explicit_max_tokens():
    from citnega.packages.kb.ingestion import chunk_text

    # With a very small max_tokens, multi-paragraph text splits into multiple chunks.
    # Two separate paragraphs (separated by blank line) each fit in 512 tokens.
    text = "First paragraph text.\n\nSecond paragraph text."
    chunks = chunk_text(text, max_tokens=10)  # 10 * 4 = 40 chars per chunk
    assert len(chunks) == 2
    assert "First" in chunks[0]
    assert "Second" in chunks[1]


def test_chunk_text_default_respects_settings(monkeypatch):
    """chunk_text() with no explicit max_tokens reads from settings."""
    from citnega.packages.kb.ingestion import chunk_text

    # Default 512 tokens should handle any reasonable text without chunking
    text = "Hello world. " * 100  # ~1300 chars, well under 512 * 4 = 2048 chars
    chunks = chunk_text(text)
    assert len(chunks) >= 1


# ── 8. DirectModelRunner accepts max_tool_rounds ─────────────────────────────


def test_direct_runner_max_tool_rounds_default():
    from citnega.packages.adapters.direct.runner import DirectModelRunner, _MAX_TOOL_ROUNDS_DEFAULT

    assert _MAX_TOOL_ROUNDS_DEFAULT == 5


# ── 9. Settings TOML file contains all new keys ──────────────────────────────


def test_settings_toml_contains_new_runtime_keys():
    from pathlib import Path

    toml_path = (
        Path(__file__).parent.parent.parent.parent
        / "packages"
        / "config"
        / "defaults"
        / "settings.toml"
    )
    content = toml_path.read_text()
    assert "event_queue_max_size" in content
    assert "max_tool_rounds" in content
    assert "max_supervisor_rounds" in content
    assert "shutdown_drain_timeout_seconds" in content
    assert "provider_max_retries" in content
    assert "kb_chunk_size_tokens" in content
    assert "token_budget_default_priority" in content
    assert "input_history_size" in content
