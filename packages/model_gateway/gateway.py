"""
ModelGateway — IModelGateway implementation.

Routes ModelRequest to the appropriate IModelProvider:
  1. If ``request.model_id`` is set, use that provider directly.
  2. Otherwise, run HybridRoutingPolicy against all registered providers.
  3. Apply rate limiting before forwarding.
  4. Emit RateLimitEvent on rate-limit errors.
  5. Update provider health_status after each request.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from citnega.packages.model_gateway.rate_limiter import TokenBucketRateLimiter
from citnega.packages.model_gateway.registry import ModelRegistry
from citnega.packages.model_gateway.routing import HybridRoutingPolicy
from citnega.packages.model_gateway.token_counter import CompositeTokenCounter
from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.protocol.events.rate_limit import RateLimitEvent
from citnega.packages.protocol.interfaces.events import IEventEmitter
from citnega.packages.protocol.interfaces.model_gateway import IModelGateway, IModelProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelInfo,
    ModelRequest,
    ModelResponse,
    TaskNeeds,
)
from citnega.packages.shared.errors import (
    ModelCapabilityError,
    NoHealthyProviderError,
    RateLimitExceededError,
)


class ModelGateway(IModelGateway):
    """
    Central model gateway with routing, rate limiting, and health tracking.

    Providers are registered at bootstrap via ``register_provider()``.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        rate_limiter: TokenBucketRateLimiter,
        event_emitter: IEventEmitter,
        session_id: str = "system",
        run_id: str = "system",
    ) -> None:
        self._registry = registry
        self._rate_limiter = rate_limiter
        self._emitter = event_emitter
        self._session_id = session_id
        self._run_id = run_id
        self._providers: dict[str, IModelProvider] = {}
        self._router = HybridRoutingPolicy(models=[])
        self._token_counter = CompositeTokenCounter()

    def register_provider(self, provider: IModelProvider) -> None:
        """Register a provider and add its model to the router."""
        self._providers[provider.model_info.model_id] = provider
        self._router.update_models(self._registry.list_all())
        model_gateway_logger.info(
            "provider_registered",
            model_id=provider.model_info.model_id,
            provider_type=provider.model_info.provider_type,
        )

    def _resolve_provider(self, request: ModelRequest) -> IModelProvider:
        """Select provider for the request, raising if none is suitable."""
        if request.model_id:
            provider = self._providers.get(request.model_id)
            if provider is None:
                raise ModelCapabilityError(
                    f"Model {request.model_id!r} is not registered."
                )
            return provider

        needs = request.needs or TaskNeeds()
        best = self._router.select_best(needs)
        provider = self._providers.get(best.model_id)
        if provider is None:
            raise NoHealthyProviderError(
                f"Routing selected {best.model_id!r} but no provider is registered for it."
            )
        return provider

    async def generate(self, request: ModelRequest) -> ModelResponse:
        provider = self._resolve_provider(request)
        model_id = provider.model_info.model_id
        provider_type = provider.model_info.provider_type

        # Estimate tokens for rate limiting
        prompt_tokens = self._token_counter.count_messages(request.messages)

        try:
            await self._rate_limiter.acquire(
                provider_type, model_id, prompt_tokens=prompt_tokens
            )
        except RateLimitExceededError as exc:
            self._emitter.emit(RateLimitEvent(
                session_id=self._session_id,
                run_id=self._run_id,
                callable_name=model_id,
                provider=provider_type,
                wait_seconds=0.0,
            ))
            raise

        model_gateway_logger.debug(
            "gateway_generate",
            model_id=model_id,
            prompt_tokens=prompt_tokens,
        )

        try:
            response = await provider.generate(request)
            self._registry.update_health(model_id, "healthy")
            # Account for completion tokens in rate limiter (TPM only, not RPM)
            await self._rate_limiter.acquire(
                provider_type, model_id,
                completion_tokens=response.usage.get("completion_tokens", 0),
                charge_rpm=False,
            )
            return response
        except Exception:
            self._registry.update_health(model_id, "degraded")
            raise

    async def stream_generate(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelChunk]:
        provider = self._resolve_provider(request)
        model_id = provider.model_info.model_id
        provider_type = provider.model_info.provider_type

        prompt_tokens = self._token_counter.count_messages(request.messages)
        try:
            await self._rate_limiter.acquire(
                provider_type, model_id, prompt_tokens=prompt_tokens
            )
        except RateLimitExceededError as exc:
            self._emitter.emit(RateLimitEvent(
                session_id=self._session_id,
                run_id=self._run_id,
                callable_name=model_id,
                provider=provider_type,
                wait_seconds=0.0,
            ))
            raise

        try:
            async for chunk in provider.stream_generate(request):
                yield chunk
            self._registry.update_health(model_id, "healthy")
        except Exception:
            self._registry.update_health(model_id, "degraded")
            raise

    async def list_models(self) -> list[ModelInfo]:
        return self._registry.list_all()

    async def health_check_all(self) -> dict[str, str]:
        """Run health checks on all registered providers concurrently."""
        async def _check(model_id: str, provider: IModelProvider) -> tuple[str, str]:
            status = await provider.health_check()
            self._registry.update_health(model_id, status)
            return model_id, status

        results = await asyncio.gather(
            *[_check(mid, p) for mid, p in self._providers.items()],
            return_exceptions=True,
        )
        return {
            mid: status
            for r in results
            if not isinstance(r, Exception)
            for mid, status in [r]  # type: ignore[misc]
        }
