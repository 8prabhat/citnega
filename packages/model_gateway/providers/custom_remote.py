"""
CustomRemoteProvider — IModelProvider for user-defined HTTP endpoints.

Supports any endpoint that accepts a JSON POST with a ``messages`` array
and returns a JSON body with ``choices[0].message.content``.

Configuration is fully driven by the model_registry.toml entry's
``framework_specific`` dict::

    [[models]]
    model_id      = "my-custom-model"
    provider_type = "custom_remote"
    ...

    [models.framework_specific]
    base_url      = "https://my.api.example.com/v1"
    api_key_env   = "MY_API_KEY"     # env var name for the key
    request_format = "openai"         # "openai" | "simple"
    health_path   = "/health"
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from citnega.packages.model_gateway.providers.base_provider import BaseProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelInfo,
    ModelRequest,
    ModelResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx


class CustomRemoteProvider(BaseProvider):
    """
    Flexible provider for custom / proprietary HTTP endpoints.

    Supports two request formats:
      - "openai"  — standard OpenAI chat/completions body
      - "simple"  — {"prompt": "<concatenated messages>", "max_tokens": N}
    """

    def __init__(
        self,
        model_info: ModelInfo,
        base_url: str,
        api_key: str = "",
        request_format: str = "openai",
        health_path: str = "/health",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_info, http_client)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._request_format = request_format
        self._health_path = health_path

    @classmethod
    def from_registry_entry(
        cls,
        model_info: ModelInfo,
        http_client: httpx.AsyncClient | None = None,
    ) -> CustomRemoteProvider:
        """Build from the model_info.framework_specific dict."""
        fs: dict[str, object] = {}
        base_url = fs.get("base_url", "http://localhost:8080")
        api_key_env = fs.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""
        return cls(
            model_info=model_info,
            base_url=base_url,
            api_key=api_key,
            request_format=fs.get("request_format", "openai"),
            health_path=fs.get("health_path", "/health"),
            http_client=http_client,
        )

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _build_payload(self, request: ModelRequest) -> dict[str, object]:
        if self._request_format == "simple":
            prompt = "\n".join(f"{m.role}: {m.content}" for m in request.messages)
            return {
                "prompt": prompt,
                "max_tokens": request.max_tokens or 1024,
                "temperature": request.temperature,
            }
        # default: openai format
        return {
            "model": self._model_info.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }

    async def _do_generate(self, request: ModelRequest) -> ModelResponse:
        payload = self._build_payload(request)
        resp = await self._http_client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()

        if self._request_format == "simple":
            content = data.get("text", data.get("content", ""))
        else:
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")

        usage = data.get("usage", {})
        return ModelResponse(
            model_id=self._model_info.model_id,
            content=content,
            tool_calls=[],
            finish_reason=data.get("choices", [{}])[0].get("finish_reason", "stop")
            if self._request_format == "openai"
            else "stop",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    async def _do_stream_generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        payload = {**self._build_payload(request), "stream": True}
        async with self._http_client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield ModelChunk(finish_reason="stop")
                        return
                    try:
                        chunk = json.loads(data_str)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        yield ModelChunk(content=content)
                    except json.JSONDecodeError:
                        pass

    async def _do_health_check(self) -> str:
        try:
            resp = await self._http_client.get(f"{self._base_url}{self._health_path}", timeout=3.0)
            return "healthy" if resp.status_code < 400 else "degraded"
        except Exception:
            return "down"
