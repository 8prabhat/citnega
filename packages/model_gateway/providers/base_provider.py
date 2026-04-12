"""
BaseProvider — shared retry + HTTP client helpers for all model providers.

Concrete providers extend this and implement:
  - ``_do_generate(request)`` → ModelResponse
  - ``_do_stream_generate(request)`` → AsyncIterator[ModelChunk]
  - ``_do_health_check()`` → str
"""

from __future__ import annotations

from abc import abstractmethod
import asyncio
from typing import TYPE_CHECKING

import httpx

from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.protocol.interfaces.model_gateway import IModelProvider
from citnega.packages.shared.errors import ProviderHTTPError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from citnega.packages.protocol.models.model_gateway import (
        ModelChunk,
        ModelInfo,
        ModelRequest,
        ModelResponse,
    )

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class BaseProvider(IModelProvider):
    """
    Shared retry and HTTP client logic.

    Subclasses inject a shared httpx.AsyncClient or let this class create
    one.  The client is managed externally (connection pooling).
    """

    def __init__(
        self,
        model_info: ModelInfo,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model_info = model_info
        self._http_client = http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    @property
    def model_info(self) -> ModelInfo:
        return self._model_info

    def supports(self, capability: str) -> bool:
        return bool(getattr(self._model_info.capabilities, capability, False))

    def count_tokens(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    # ------------------------------------------------------------------
    # IModelProvider — with retry wrapper
    # ------------------------------------------------------------------

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self._with_retry(self._do_generate, request)

    async def stream_generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        # Streaming is not retried — let callers handle partial responses
        async for chunk in self._do_stream_generate(request):
            yield chunk

    async def health_check(self) -> str:
        try:
            return await self._do_health_check()
        except Exception as exc:
            model_gateway_logger.warning(
                "provider_health_check_failed",
                model_id=self._model_info.model_id,
                error=str(exc),
            )
            return "down"

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    async def _with_retry(self, fn, request: ModelRequest) -> ModelResponse:  # type: ignore[type-arg]
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await fn(request)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRY_STATUSES:
                    raise ProviderHTTPError(
                        f"HTTP {exc.response.status_code} from "
                        f"{self._model_info.model_id}: {exc.response.text[:200]}"
                    ) from exc
                last_exc = exc
                wait = 2 ** (attempt - 1)
                model_gateway_logger.warning(
                    "provider_retry",
                    model_id=self._model_info.model_id,
                    attempt=attempt,
                    status=exc.response.status_code,
                    wait=wait,
                )
                await asyncio.sleep(wait)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                wait = 2 ** (attempt - 1)
                model_gateway_logger.warning(
                    "provider_retry_connection",
                    model_id=self._model_info.model_id,
                    attempt=attempt,
                    error=str(exc),
                    wait=wait,
                )
                await asyncio.sleep(wait)

        raise ProviderHTTPError(
            f"Provider {self._model_info.model_id} failed after {_MAX_RETRIES} retries: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Abstract hooks
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    async def _do_stream_generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]: ...

    @abstractmethod
    async def _do_health_check(self) -> str: ...
