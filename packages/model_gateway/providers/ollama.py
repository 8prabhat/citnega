"""
OllamaProvider — IModelProvider for local Ollama server.

Ollama REST API:
  POST /api/chat       — non-streaming: {"stream": false}
  POST /api/chat       — streaming:     {"stream": true}  (NDJSON)
  GET  /api/tags       — list available models
  GET  /api/show       — health / model info
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from citnega.packages.model_gateway.providers.base_provider import BaseProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx


def _to_ollama_messages(messages: list[ModelMessage]) -> list[dict[str, object]]:
    result = []
    for m in messages:
        entry: dict[str, object] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        result.append(entry)
    return result


class OllamaProvider(BaseProvider):
    """Provider for local Ollama inference server."""

    def __init__(
        self,
        model_info: ModelInfo,
        base_url: str = "http://localhost:11434",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(model_info, http_client)
        self._base_url = base_url.rstrip("/")

    async def _do_generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, object] = {
            "model": self._model_info.model_name,
            "messages": _to_ollama_messages(request.messages),
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.max_tokens:
            payload["options"] = {**payload["options"], "num_predict": request.max_tokens}  # type: ignore[arg-type]
        if request.tools:
            payload["tools"] = request.tools

        resp = await self._http_client.post(f"{self._base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        message = data.get("message", {})
        tool_calls: list[dict[str, object]] = message.get("tool_calls", [])
        usage = data.get("usage", {})

        return ModelResponse(
            model_id=self._model_info.model_id,
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason", "stop"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        )

    async def _do_stream_generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        payload: dict[str, object] = {
            "model": self._model_info.model_name,
            "messages": _to_ollama_messages(request.messages),
            "stream": True,
            "options": {"temperature": request.temperature},
        }
        if request.tools:
            payload["tools"] = request.tools

        async with self._http_client.stream(
            "POST", f"{self._base_url}/api/chat", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = chunk.get("message", {})
                content = message.get("content", "") or ""
                thinking = message.get("thinking", "") or ""
                done = chunk.get("done", False)
                finish_reason: str | None = chunk.get("done_reason") if done else None
                tool_call_delta = message.get("tool_calls")
                # Emit two separate chunks when both fields present (rare but possible)
                if thinking:
                    yield ModelChunk(thinking=thinking, finish_reason=None)
                if content or tool_call_delta or done:
                    yield ModelChunk(
                        content=content or None,
                        tool_call_delta=tool_call_delta,
                        finish_reason=finish_reason,
                    )

    async def _do_health_check(self) -> str:
        try:
            resp = await self._http_client.get(f"{self._base_url}/api/tags", timeout=3.0)
            if resp.status_code == 200:
                return "healthy"
            return "degraded"
        except Exception:
            return "down"
