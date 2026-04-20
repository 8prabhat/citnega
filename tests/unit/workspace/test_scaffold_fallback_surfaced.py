"""Tests that scaffold.py surfaces LLM fallback via warning log and on_status callback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.workspace.scaffold import ScaffoldGenerator
from citnega.packages.workspace.templates import ScaffoldSpec


def _make_spec() -> ScaffoldSpec:
    return ScaffoldSpec(
        kind="tool",
        name="dummy_tool",
        class_name="DummyTool",
        description="A dummy tool for testing.",
    )


@pytest.mark.asyncio
async def test_generate_logs_warning_on_llm_failure():
    failing_gateway = MagicMock()
    failing_gateway.generate = AsyncMock(side_effect=RuntimeError("LLM offline"))

    gen = ScaffoldGenerator(model_gateway=failing_gateway)
    spec = _make_spec()

    mock_logger = MagicMock()
    with patch("structlog.get_logger", return_value=mock_logger):
        source = await gen.generate(spec)

    assert "DummyTool" in source or "dummy_tool" in source
    mock_logger.warning.assert_called_once()
    call_kwargs = mock_logger.warning.call_args
    assert "scaffold_llm_unavailable_fallback" in call_kwargs[0] or "scaffold_llm_unavailable_fallback" in str(call_kwargs)


@pytest.mark.asyncio
async def test_generate_streaming_calls_on_status_on_llm_failure():
    failing_gateway = MagicMock()
    failing_gateway.stream_generate = MagicMock(side_effect=RuntimeError("stream broken"))

    gen = ScaffoldGenerator(model_gateway=failing_gateway)
    spec = _make_spec()

    chunks: list[str] = []
    status_messages: list[str] = []

    async def on_chunk(c: str) -> None:
        chunks.append(c)

    async def on_status(s: str) -> None:
        status_messages.append(s)

    source = await gen.generate_streaming(spec, on_chunk, on_status=on_status)

    assert source
    assert any("LLM unavailable" in s or "template" in s.lower() for s in status_messages), (
        f"Expected LLM-unavailable notice in status messages, got: {status_messages}"
    )


@pytest.mark.asyncio
async def test_generate_streaming_no_on_status_still_works_on_llm_failure():
    failing_gateway = MagicMock()
    failing_gateway.stream_generate = MagicMock(side_effect=RuntimeError("stream broken"))

    gen = ScaffoldGenerator(model_gateway=failing_gateway)
    spec = _make_spec()

    chunks: list[str] = []

    async def on_chunk(c: str) -> None:
        chunks.append(c)

    # Should not raise even without on_status
    source = await gen.generate_streaming(spec, on_chunk)
    assert source
    assert chunks  # fallback was delivered as a chunk
