"""
VLLMProvider — IModelProvider for vLLM inference server.

vLLM exposes an OpenAI-compatible API at /v1/chat/completions.
This provider extends OpenAICompatibleProvider with vLLM-specific
health check (GET /health) and guided decoding support.
"""

from __future__ import annotations

import httpx

from citnega.packages.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from citnega.packages.protocol.models.model_gateway import ModelInfo


class VLLMProvider(OpenAICompatibleProvider):
    """
    Provider for vLLM inference server.

    Identical to OpenAICompatibleProvider but with:
      - /health endpoint for health checks (vLLM-specific)
      - ``extra_body`` support for guided decoding
    """

    def __init__(
        self,
        model_info: ModelInfo,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "EMPTY",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_info, base_url=base_url, api_key=api_key, http_client=http_client)

    async def _do_health_check(self) -> str:
        """vLLM provides /health endpoint (not /models)."""
        try:
            # vLLM health endpoint is at the server root, not under /v1
            health_url = self._base_url.replace("/v1", "").rstrip("/") + "/health"
            resp = await self._http_client.get(health_url, timeout=3.0)
            return "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            return "down"
