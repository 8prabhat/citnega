"""Unit tests for ModelGateway, routing policies, rate limiter, and token counter."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
import httpx

from citnega.packages.model_gateway.gateway import ModelGateway
from citnega.packages.model_gateway.rate_limiter import TokenBucketRateLimiter
from citnega.packages.model_gateway.registry import ModelRegistry
from citnega.packages.model_gateway.routing import (
    HybridRoutingPolicy,
    NoSuitableModelError,
    StaticPriorityPolicy,
)
from citnega.packages.model_gateway.token_counter import CharApproxCounter, CompositeTokenCounter
from citnega.packages.model_gateway.providers.ollama import OllamaProvider
from citnega.packages.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelCapabilityFlags,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TaskNeeds,
)
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.shared.errors import RateLimitExceededError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_info(
    model_id: str = "test-model",
    provider_type: str = "ollama",
    local: bool = True,
    priority: int = 80,
    tool_calling: bool = True,
    health: str = "healthy",
    preferred_for: list[str] | None = None,
) -> ModelInfo:
    return ModelInfo(
        model_id=model_id,
        provider_type=provider_type,
        model_name=model_id,
        local=local,
        priority=priority,
        health_status=health,
        preferred_for=preferred_for or ["general"],
        capabilities=ModelCapabilityFlags(
            local_only=local,
            supports_streaming=True,
            supports_tool_calling=tool_calling,
            max_context_tokens=8192,
        ),
    )


def _request(model_id: str | None = None, needs: TaskNeeds | None = None) -> ModelRequest:
    return ModelRequest(
        model_id=model_id,
        messages=[ModelMessage(role="user", content="Hello")],
        needs=needs,
    )


def _mock_emitter() -> EventEmitter:
    emitter = MagicMock(spec=EventEmitter)
    emitter.emit = MagicMock()
    return emitter


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------

class TestModelRegistry:
    def test_register_and_get(self) -> None:
        reg = ModelRegistry()
        info = _model_info("m1")
        reg.register(info)
        assert reg.get("m1") == info

    def test_list_all(self) -> None:
        reg = ModelRegistry()
        reg.register(_model_info("a"))
        reg.register(_model_info("b"))
        assert len(reg.list_all()) == 2

    def test_list_by_capability(self) -> None:
        reg = ModelRegistry()
        reg.register(_model_info("tool-model", tool_calling=True))
        reg.register(_model_info("no-tool", tool_calling=False))
        results = reg.list_by_capability(supports_tool_calling=True)
        assert all(r.capabilities.supports_tool_calling for r in results)

    def test_update_health(self) -> None:
        reg = ModelRegistry()
        reg.register(_model_info("m1", health="healthy"))
        reg.update_health("m1", "down")
        assert reg.get("m1").health_status == "down"

    def test_unknown_model_returns_none(self) -> None:
        reg = ModelRegistry()
        assert reg.get("nonexistent") is None


# ---------------------------------------------------------------------------
# StaticPriorityPolicy
# ---------------------------------------------------------------------------

class TestStaticPriorityPolicy:
    def test_filters_unhealthy(self) -> None:
        policy = StaticPriorityPolicy()
        models = [
            _model_info("good", health="healthy", priority=90),
            _model_info("bad", health="down", priority=100),
        ]
        result = policy.select(models, TaskNeeds())
        ids = [m.model_id for m in result]
        assert "bad" not in ids
        assert "good" in ids

    def test_respects_local_only(self) -> None:
        policy = StaticPriorityPolicy()
        models = [
            _model_info("remote", local=False),
            _model_info("local", local=True),
        ]
        result = policy.select(models, TaskNeeds(local_only=True))
        assert all(m.model_info.local if hasattr(m, 'model_info') else m.local for m in result)

    def test_priority_order(self) -> None:
        policy = StaticPriorityPolicy()
        models = [
            _model_info("low", priority=10, preferred_for=["general"]),
            _model_info("high", priority=90, preferred_for=["general"]),
        ]
        result = policy.select(models, TaskNeeds(task_type="general"))
        assert result[0].model_id == "high"

    def test_preferred_for_wins_over_priority(self) -> None:
        policy = StaticPriorityPolicy()
        models = [
            _model_info("generic-high", priority=95, preferred_for=["other"]),
            _model_info("code-specialist", priority=50, preferred_for=["code"]),
        ]
        result = policy.select(models, TaskNeeds(task_type="code"))
        assert result[0].model_id == "code-specialist"


# ---------------------------------------------------------------------------
# HybridRoutingPolicy
# ---------------------------------------------------------------------------

class TestHybridRoutingPolicy:
    def test_select_best(self) -> None:
        models = [_model_info("m1", priority=80), _model_info("m2", priority=60)]
        policy = HybridRoutingPolicy(models)
        best = policy.select_best(TaskNeeds())
        assert best.model_id == "m1"

    def test_no_models_raises(self) -> None:
        policy = HybridRoutingPolicy([])
        with pytest.raises(NoSuitableModelError):
            policy.select_best(TaskNeeds())

    def test_fallback_when_no_capability_match(self) -> None:
        # All models lack reasoning, but fallback should still return something
        models = [_model_info("m1", priority=70)]
        policy = HybridRoutingPolicy(models)
        # reasoning_required=True but m1 doesn't support it
        # fallback should still return m1 as it's healthy
        best = policy.select_best(TaskNeeds(reasoning_required=True))
        assert best.model_id == "m1"


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter
# ---------------------------------------------------------------------------

class TestTokenBucketRateLimiter:
    @pytest.mark.asyncio
    async def test_within_limit_passes(self) -> None:
        rl = TokenBucketRateLimiter()
        rl.set_limits("ollama", "m1", rpm=60, tpm=100_000)
        await rl.acquire("ollama", "m1", prompt_tokens=100)

    @pytest.mark.asyncio
    async def test_exceeds_rpm_raises(self) -> None:
        rl = TokenBucketRateLimiter()
        rl.set_limits("ollama", "m1", rpm=1, tpm=1_000_000)
        await rl.acquire("ollama", "m1")  # consume the 1 RPM token
        with pytest.raises(RateLimitExceededError, match="RPM"):
            await rl.acquire("ollama", "m1")

    @pytest.mark.asyncio
    async def test_no_limits_configured_passes(self) -> None:
        rl = TokenBucketRateLimiter()
        # No limits set for this key — should not raise
        await rl.acquire("unknown", "model", prompt_tokens=999)


# ---------------------------------------------------------------------------
# CharApproxCounter
# ---------------------------------------------------------------------------

class TestCharApproxCounter:
    def test_count_non_empty(self) -> None:
        counter = CharApproxCounter()
        assert counter.count("hello world") > 0

    def test_count_empty_returns_one(self) -> None:
        counter = CharApproxCounter()
        assert counter.count("") == 1

    def test_count_messages(self) -> None:
        counter = CharApproxCounter()
        msgs = [
            ModelMessage(role="user", content="Hello, how are you?"),
            ModelMessage(role="assistant", content="I am fine, thank you!"),
        ]
        total = counter.count_messages(msgs)
        assert total > 0


# ---------------------------------------------------------------------------
# OllamaProvider (mock HTTP)
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        info = _model_info("gemma3", provider_type="ollama")
        response_body = {
            "message": {"role": "assistant", "content": "Hello!", "tool_calls": []},
            "done": True,
            "done_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        async with respx.mock:
            respx.post("http://localhost:11434/api/chat").mock(
                return_value=httpx.Response(200, json=response_body)
            )
            async with httpx.AsyncClient() as client:
                provider = OllamaProvider(info, http_client=client)
                req = _request("gemma3")
                result = await provider.generate(req)

        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        info = _model_info("gemma3", provider_type="ollama")
        async with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                return_value=httpx.Response(200, json={"models": []})
            )
            async with httpx.AsyncClient() as client:
                provider = OllamaProvider(info, http_client=client)
                status = await provider.health_check()
        assert status == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_down_on_connection_error(self) -> None:
        info = _model_info("gemma3", provider_type="ollama")
        async with respx.mock:
            respx.get("http://localhost:11434/api/tags").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            async with httpx.AsyncClient() as client:
                provider = OllamaProvider(info, http_client=client)
                status = await provider.health_check()
        assert status == "down"


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider (mock HTTP)
# ---------------------------------------------------------------------------

class TestOpenAICompatibleProvider:
    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        info = _model_info("gpt-4o", provider_type="openai_compatible", local=False)
        response_body = {
            "choices": [{
                "message": {"role": "assistant", "content": "Hi there!"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
        }
        async with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=response_body)
            )
            async with httpx.AsyncClient() as client:
                provider = OpenAICompatibleProvider(
                    info, base_url="https://api.openai.com/v1", api_key="sk-test",
                    http_client=client,
                )
                result = await provider.generate(_request("gpt-4o"))

        assert result.content == "Hi there!"
        assert result.usage["total_tokens"] == 11

    @pytest.mark.asyncio
    async def test_retries_on_500(self) -> None:
        info = _model_info("gpt-4o", provider_type="openai_compatible", local=False)
        call_count = 0

        async with respx.mock:
            def _handler(request: httpx.Request) -> httpx.Response:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    return httpx.Response(500, text="Internal Server Error")
                return httpx.Response(200, json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                })

            respx.post("https://api.openai.com/v1/chat/completions").mock(
                side_effect=_handler
            )
            async with httpx.AsyncClient() as client:
                provider = OpenAICompatibleProvider(
                    info, base_url="https://api.openai.com/v1",
                    http_client=client,
                )
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await provider.generate(_request("gpt-4o"))

        assert result.content == "ok"
        assert call_count == 3


# ---------------------------------------------------------------------------
# ModelGateway (end-to-end with mock provider)
# ---------------------------------------------------------------------------

class TestModelGateway:
    def _make_gateway(self) -> tuple[ModelGateway, MagicMock]:
        registry = ModelRegistry()
        rl = TokenBucketRateLimiter()
        emitter = _mock_emitter()
        gw = ModelGateway(registry, rl, emitter)

        mock_provider = MagicMock(spec=["generate", "stream_generate", "health_check",
                                         "model_info", "supports", "count_tokens"])
        info = _model_info("test-model")
        mock_provider.model_info = info
        mock_provider.generate = AsyncMock(return_value=ModelResponse(
            model_id="test-model",
            content="test response",
            finish_reason="stop",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        ))
        registry.register(info)
        gw.register_provider(mock_provider)
        return gw, mock_provider

    @pytest.mark.asyncio
    async def test_generate_routes_to_provider(self) -> None:
        gw, mock_provider = self._make_gateway()
        result = await gw.generate(_request("test-model"))
        assert result.content == "test response"
        mock_provider.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_unknown_model_raises(self) -> None:
        gw, _ = self._make_gateway()
        from citnega.packages.shared.errors import ModelCapabilityError
        with pytest.raises(ModelCapabilityError):
            await gw.generate(_request("nonexistent-model"))

    @pytest.mark.asyncio
    async def test_list_models(self) -> None:
        gw, _ = self._make_gateway()
        models = await gw.list_models()
        assert any(m.model_id == "test-model" for m in models)

    @pytest.mark.asyncio
    async def test_health_check_all(self) -> None:
        gw, mock_provider = self._make_gateway()
        mock_provider.health_check = AsyncMock(return_value="healthy")
        results = await gw.health_check_all()
        assert "test-model" in results
        assert results["test-model"] == "healthy"

    @pytest.mark.asyncio
    async def test_rate_limit_emits_event(self) -> None:
        registry = ModelRegistry()
        rl = TokenBucketRateLimiter()
        rl.set_limits("ollama", "rate-model", rpm=1, tpm=1_000_000)
        emitter = _mock_emitter()
        gw = ModelGateway(registry, rl, emitter)

        info = _model_info("rate-model")
        mock_provider = MagicMock()
        mock_provider.model_info = info
        mock_provider.generate = AsyncMock(return_value=ModelResponse(
            model_id="rate-model", content="ok", finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        ))
        registry.register(info)
        gw.register_provider(mock_provider)

        # First request succeeds
        await gw.generate(_request("rate-model"))
        # Second request exceeds RPM
        with pytest.raises(RateLimitExceededError):
            await gw.generate(_request("rate-model"))

        # RateLimitEvent should have been emitted
        emitter.emit.assert_called()
