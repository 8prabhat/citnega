"""Tests that retry backoff includes random jitter (C1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


@pytest.fixture()
def provider():
    from citnega.packages.model_gateway.providers.base_provider import BaseProvider
    from citnega.packages.protocol.models.model_gateway import ModelInfo

    model_info = MagicMock(spec=ModelInfo)
    model_info.model_id = "test-model"
    model_info.provider_type = "test"

    class ConcreteProvider(BaseProvider):
        async def _do_generate(self, request):
            raise httpx.ConnectError("refused")

        async def _do_stream_generate(self, request):
            raise httpx.ConnectError("refused")
            yield  # make it an async generator

        async def _do_health_check(self):
            return "healthy"

    return ConcreteProvider(model_info)


async def test_retry_wait_includes_jitter(provider) -> None:
    """Each retry sleep call must include a jitter component > 0."""
    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    from citnega.packages.protocol.models.model_gateway import ModelRequest

    request = MagicMock(spec=ModelRequest)
    request.model_id = "test-model"
    request.needs = None

    with (
        patch("asyncio.sleep", side_effect=_fake_sleep),
        patch("citnega.packages.model_gateway.providers.base_provider._get_max_retries", return_value=3),
        patch("citnega.packages.model_gateway.circuit_breaker.get_circuit_breaker") as mock_cb,
        patch("random.uniform", return_value=0.42) as mock_uniform,
    ):
        mock_cb.return_value = MagicMock(raise_if_open=MagicMock(), record_failure=MagicMock(), record_success=MagicMock())
        with pytest.raises(Exception):
            await provider.generate(request)

    # random.uniform was called for each retry
    assert mock_uniform.call_count >= 1
    # Each sleep value must include the jitter (0.42)
    for wait in sleep_calls:
        assert wait == int(wait - 0.42) + 0.42 or (wait % 1) == pytest.approx(0.42)


async def test_stream_retry_wait_includes_jitter(provider) -> None:
    """Stream retries must also include jitter."""
    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    from citnega.packages.protocol.models.model_gateway import ModelRequest

    request = MagicMock(spec=ModelRequest)
    request.model_id = "test-model"
    request.needs = None

    with (
        patch("asyncio.sleep", side_effect=_fake_sleep),
        patch("citnega.packages.model_gateway.providers.base_provider._get_streaming_max_retries", return_value=2),
        patch("random.uniform", return_value=0.25) as mock_uniform,
    ):
        with pytest.raises(Exception):
            chunks = []
            async for chunk in provider.stream_generate(request):
                chunks.append(chunk)

    assert mock_uniform.call_count >= 1
    for wait in sleep_calls:
        # Base wait (power of 2) plus jitter (0.25)
        assert wait >= 0.25
