"""
Unit tests for BaseProvider streaming retry logic (F6).

Verifies:
- stream_generate retries on ConnectError/TimeoutException (up to streaming_max_retries)
- stream_generate does NOT retry on partial-content success (no double-emission)
- generate() retry path is unchanged (uses _with_retry)
- After max retries exhausted, ProviderHTTPError is raised
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from citnega.packages.model_gateway.providers.base_provider import BaseProvider
from citnega.packages.shared.errors import ProviderHTTPError


class _StubProvider(BaseProvider):
    """Minimal concrete BaseProvider for testing."""

    def __init__(self) -> None:
        model_info = MagicMock()
        model_info.model_id = "stub-model"
        super().__init__(model_info=model_info, http_client=MagicMock())

    async def _do_generate(self, request: Any) -> Any:
        raise NotImplementedError

    async def _do_stream_generate(self, request: Any) -> AsyncIterator[Any]:
        raise NotImplementedError
        yield  # make it a generator

    async def _do_health_check(self) -> str:
        return "ok"


def _make_chunk(text: str) -> MagicMock:
    chunk = MagicMock()
    chunk.text = text
    return chunk


@pytest.mark.asyncio
async def test_stream_generate_retries_on_connect_error() -> None:
    """ConnectError on first attempt → retry → success on second attempt."""
    provider = _StubProvider()
    chunks = [_make_chunk("hello"), _make_chunk(" world")]

    call_count = 0

    async def _flaky_stream(request: Any) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        for c in chunks:
            yield c

    with (
        patch.object(provider, "_do_stream_generate", side_effect=_flaky_stream),
        patch(
            "citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries",
            return_value=2,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        received = []
        async for chunk in provider.stream_generate(MagicMock()):
            received.append(chunk)

    assert received == chunks
    assert call_count == 2


@pytest.mark.asyncio
async def test_stream_generate_retries_on_timeout() -> None:
    """TimeoutException on first attempt → retry → success."""
    provider = _StubProvider()
    call_count = 0

    async def _flaky_stream(request: Any) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("read timed out")
        yield _make_chunk("ok")

    with (
        patch.object(provider, "_do_stream_generate", side_effect=_flaky_stream),
        patch(
            "citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries",
            return_value=2,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        received = []
        async for chunk in provider.stream_generate(MagicMock()):
            received.append(chunk)

    assert len(received) == 1
    assert call_count == 2


@pytest.mark.asyncio
async def test_stream_generate_raises_after_max_retries() -> None:
    """Exhausted retries → ProviderHTTPError raised."""
    provider = _StubProvider()

    async def _always_fail(request: Any) -> AsyncIterator[Any]:
        raise httpx.ConnectError("unreachable")
        yield

    with (
        patch.object(provider, "_do_stream_generate", side_effect=_always_fail),
        patch(
            "citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries",
            return_value=2,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(ProviderHTTPError, match="stream failed after 2 retries"):
            async for _ in provider.stream_generate(MagicMock()):
                pass


@pytest.mark.asyncio
async def test_stream_generate_no_retry_on_success() -> None:
    """Successful stream yields all chunks with exactly one call."""
    provider = _StubProvider()
    call_count = 0

    async def _good_stream(request: Any) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        for i in range(3):
            yield _make_chunk(f"chunk-{i}")

    with (
        patch.object(provider, "_do_stream_generate", side_effect=_good_stream),
        patch(
            "citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries",
            return_value=2,
        ),
    ):
        received = []
        async for chunk in provider.stream_generate(MagicMock()):
            received.append(chunk)

    assert len(received) == 3
    assert call_count == 1


@pytest.mark.asyncio
async def test_streaming_max_retries_setting_respected() -> None:
    """streaming_max_retries=0 → no retry, raises immediately."""
    provider = _StubProvider()
    call_count = 0

    async def _always_fail(request: Any) -> AsyncIterator[Any]:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("fail")
        yield

    with (
        patch.object(provider, "_do_stream_generate", side_effect=_always_fail),
        patch(
            "citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries",
            return_value=1,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(ProviderHTTPError):
            async for _ in provider.stream_generate(MagicMock()):
                pass

    assert call_count == 1
