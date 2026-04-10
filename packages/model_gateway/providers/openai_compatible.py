"""
OpenAICompatibleProvider — IModelProvider for OpenAI-API-compatible endpoints.

Supports: OpenAI, Azure OpenAI, LM Studio, Together AI, Groq, and any server
that implements the /v1/chat/completions endpoint.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from citnega.packages.model_gateway.providers.base_provider import BaseProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)


def _to_oai_messages(messages: list[ModelMessage]) -> list[dict[str, object]]:
    result = []
    for m in messages:
        entry: dict[str, object] = {"role": m.role, "content": m.content}
        if m.name:
            entry["name"] = m.name
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        result.append(entry)
    return result


class OpenAICompatibleProvider(BaseProvider):
    """Provider for OpenAI-API-compatible endpoints."""

    def __init__(
        self,
        model_info: ModelInfo,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_info, http_client)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def _do_generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, object] = {
            "model":       self._model_info.model_name,
            "messages":    _to_oai_messages(request.messages),
            "stream":      False,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
        if request.response_format:
            payload["response_format"] = request.response_format

        resp = await self._http_client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        return ModelResponse(
            model_id=self._model_info.model_id,
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason", "stop"),
            usage={
                "prompt_tokens":     usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens":      usage.get("total_tokens", 0),
            },
        )

    async def _do_stream_generate(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelChunk]:
        payload: dict[str, object] = {
            "model":       self._model_info.model_name,
            "messages":    _to_oai_messages(request.messages),
            "stream":      True,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools

        async with self._http_client.stream(
            "POST",
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    yield ModelChunk(finish_reason="stop")
                    return
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content")
                tool_calls = delta.get("tool_calls")
                finish_reason = choice.get("finish_reason")
                yield ModelChunk(
                    content=content,
                    tool_call_delta=tool_calls[0] if tool_calls else None,
                    finish_reason=finish_reason,
                )

    async def _do_health_check(self) -> str:
        try:
            resp = await self._http_client.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=5.0,
            )
            return "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            return "down"
