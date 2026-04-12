"""Shared helpers for resolving Citnega model IDs into ADK model references."""

from __future__ import annotations

from typing import Any


def make_lite_llm(model_str: str) -> Any:
    """Return a LiteLLM-backed ADK model wrapper."""
    try:
        from google.adk.models.lite_llm import LiteLlm  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "LiteLLM support requires: pip install 'google-adk[extensions]' litellm"
        ) from exc
    return LiteLlm(model=model_str)


def resolve_adk_model_reference(model_id: str | None) -> Any:
    """
    Resolve a Citnega model identifier into an ADK-compatible model reference.

    Resolution order:
    1. Explicit LiteLLM identifier (``ollama/...`` or ``litellm/...``)
    2. Citnega model-registry ID backed by an Ollama provider
    3. Raw provider-native string for framework-native models
    """
    mid = (model_id or "").strip()
    if not mid:
        return mid

    if mid.startswith(("ollama/", "litellm/")):
        return make_lite_llm(mid)

    try:
        from citnega.packages.model_gateway.registry import ModelRegistry

        registry = ModelRegistry()
        registry.load()
        for info in registry.list_all():
            if info.model_id == mid and info.provider_type == "ollama":
                return make_lite_llm(f"ollama/{info.model_name}")
    except Exception:
        pass

    return mid
