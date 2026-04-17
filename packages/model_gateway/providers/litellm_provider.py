"""
LiteLLMProvider — universal cloud provider via the litellm library.

Handles any provider that litellm supports: OpenAI, Anthropic, Azure OpenAI,
Google Gemini, Groq, Cohere, Mistral, Bedrock, and 100+ others.

Model name format (litellm routing convention):
  "openai/gpt-4o"
  "anthropic/claude-opus-4-5"
  "azure/my-deployment-name"
  "gemini/gemini-2.5-pro"
  "groq/llama3-70b-8192"
  "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"

API key / auth:
  - Plain api_key:   set ProviderConfig.api_key (static string or ${ENV_VAR})
  - PEM-based auth:  set ProviderConfig.pem_file + auth_mode + extra fields;
                     a PEMCredential is built at startup and called before each
                     request to get a fresh (cached) token.

Extra pass-through kwargs (e.g. api_version for Azure) are forwarded directly
to litellm.acompletion so you never need to touch Python code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.model_gateway.providers.base_provider import BaseProvider
from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from citnega.packages.model_gateway.auth.pem_auth import PEMCredential
    from citnega.packages.protocol.models.model_gateway import ModelInfo, ModelRequest


def _to_litellm_messages(messages) -> list[dict[str, Any]]:
    result = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if getattr(m, "name", None):
            entry["name"] = m.name
        if getattr(m, "tool_call_id", None):
            entry["tool_call_id"] = m.tool_call_id
        if getattr(m, "tool_calls", None):
            entry["tool_calls"] = m.tool_calls
        result.append(entry)
    return result


class LiteLLMProvider(BaseProvider):
    """
    Wraps litellm so any provider config in models.yaml routes correctly.

    ``credential`` is optional — it is only set when ``auth_mode`` is not
    ``api_key``.  When present, its ``get_token()`` is called before each
    request and the result is passed as ``api_key`` to litellm.  The token
    is cached internally by the credential object.
    """

    def __init__(
        self,
        model_info: ModelInfo,
        api_key: str = "",
        base_url: str = "",
        credential: PEMCredential | None = None,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> None:
        # LiteLLM manages its own HTTP; we don't pass an httpx client
        super().__init__(model_info, http_client=None)
        self._api_key = api_key
        self._base_url = base_url
        self._credential = credential
        self._extra = extra_kwargs or {}

    async def _resolve_api_key(self) -> str:
        """Return a live API key — from PEM credential if set, else the static key."""
        if self._credential is not None:
            return await self._credential.get_token()
        return self._api_key

    async def _call_kwargs(self, request: ModelRequest) -> dict[str, Any]:
        api_key = await self._resolve_api_key()
        kw: dict[str, Any] = {
            "model": self._model_info.model_name,
            "messages": _to_litellm_messages(request.messages),
            "temperature": request.temperature,
        }
        if request.max_tokens:
            kw["max_tokens"] = request.max_tokens
        if request.tools:
            kw["tools"] = request.tools
        if request.response_format:
            kw["response_format"] = request.response_format
        if api_key:
            kw["api_key"] = api_key
        if self._base_url:
            kw["api_base"] = self._base_url
        # Forward provider-specific extras (e.g. api_version for Azure)
        kw.update(self._extra)
        return kw

    async def _do_generate(self, request: ModelRequest) -> ModelResponse:
        import litellm

        kw = await self._call_kwargs(request)
        resp = await litellm.acompletion(**kw)

        choice = resp.choices[0]
        msg = choice.message
        usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})()

        return ModelResponse(
            model_id=self._model_info.model_id,
            content=getattr(msg, "content", None) or "",
            tool_calls=getattr(msg, "tool_calls", None) or [],
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            },
        )

    async def _do_stream_generate(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        import litellm

        kw = {**await self._call_kwargs(request), "stream": True}
        response = await litellm.acompletion(**kw)

        async for chunk in response:
            choices = getattr(chunk, "choices", [])
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            tool_calls = getattr(delta, "tool_calls", None)
            finish_reason = getattr(choice, "finish_reason", None)
            yield ModelChunk(
                content=content,
                tool_call_delta=tool_calls[0] if tool_calls else None,
                finish_reason=finish_reason,
            )

    async def _do_health_check(self) -> str:
        # litellm has no generic health endpoint; defer to caller
        return "healthy"
