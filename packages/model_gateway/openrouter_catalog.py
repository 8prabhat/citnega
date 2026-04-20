"""
OpenRouter model catalog — bundled list with optional live-fetch from the API.

Uses LiteLLMProvider internally (already handles openrouter/model-id prefix).
No new provider class needed — this module only manages the model list.
"""

from __future__ import annotations

import time
from typing import Any

BUNDLED_MODELS: list[dict[str, Any]] = [
    {"id": "anthropic/claude-opus-4", "name": "Claude Opus 4", "context_length": 200000},
    {"id": "anthropic/claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "context_length": 200000},
    {"id": "anthropic/claude-haiku-4-5", "name": "Claude Haiku 4.5", "context_length": 200000},
    {"id": "openai/gpt-4o", "name": "GPT-4o", "context_length": 128000},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "context_length": 128000},
    {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash (free)", "context_length": 1048576},
    {"id": "google/gemini-2.5-pro-preview", "name": "Gemini 2.5 Pro Preview", "context_length": 1048576},
    {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B Instruct", "context_length": 131072},
    {"id": "mistralai/mistral-large", "name": "Mistral Large", "context_length": 131072},
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "context_length": 65536},
    {"id": "cohere/command-r-plus", "name": "Command R+", "context_length": 131072},
    {"id": "qwen/qwen-2.5-72b-instruct", "name": "Qwen 2.5 72B Instruct", "context_length": 131072},
]

_LIVE_FETCH_TTL = 3600.0  # seconds between live catalog refreshes


class OpenRouterCatalog:
    """
    Fetch and cache the list of models available on OpenRouter.

    Falls back to BUNDLED_MODELS on any network error so the UI always has
    a non-empty list without requiring a live API key.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._cached: list[dict[str, Any]] = []
        self._fetched_at: float = 0.0

    async def list_models(self) -> list[dict[str, Any]]:
        """Return models from cache (TTL=1h) or live API, with bundled fallback."""
        if self._cached and time.monotonic() - self._fetched_at < _LIVE_FETCH_TTL:
            return self._cached

        if not self._api_key:
            return BUNDLED_MODELS

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                r.raise_for_status()
                data = r.json().get("data", [])
                if data:
                    # Normalise to our schema
                    self._cached = [
                        {
                            "id": m.get("id", ""),
                            "name": m.get("name", m.get("id", "")),
                            "context_length": m.get("context_length", 0),
                        }
                        for m in data
                        if m.get("id")
                    ]
                    self._fetched_at = time.monotonic()
                    return self._cached
        except Exception:
            pass

        return BUNDLED_MODELS
