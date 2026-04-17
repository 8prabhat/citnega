"""
ProviderFactory — single authority for creating IModelProvider instances.

All provider construction logic lives here.  Callers never import a
concrete provider class directly — they ask the factory.

Usage::

    factory = ProviderFactory(yaml_config)
    provider = factory.build(model_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from citnega.packages.protocol.models.model_gateway import ModelCapabilityFlags, ModelInfo

if TYPE_CHECKING:
    from citnega.packages.model_gateway.yaml_config import ModelEntry, ModelYAMLConfig
    from citnega.packages.protocol.interfaces.model_gateway import IModelProvider

# Shared HTTP client — reused across providers for connection pooling
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)


class ProviderFactory:
    """
    Builds IModelProvider instances from a ModelYAMLConfig.

    A single shared ``httpx.AsyncClient`` is used for all providers to
    benefit from connection pooling.  Call ``aclose()`` when done.
    """

    def __init__(self, config: ModelYAMLConfig) -> None:
        self._config = config
        self._http_client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
        # Cache built providers so the same instance is reused
        self._cache: dict[str, IModelProvider] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, model_id: str) -> IModelProvider:
        """
        Return (or build and cache) an IModelProvider for *model_id*.

        Raises:
            KeyError: if *model_id* is not in the YAML config.
            ValueError: if the provider type is not supported.
        """
        if model_id in self._cache:
            return self._cache[model_id]

        entry = self._find_entry(model_id)
        provider = self._build_from_entry(entry)
        self._cache[model_id] = provider
        return provider

    def build_default(self) -> IModelProvider | None:
        """Return the provider for the configured default model, or None."""
        if not self._config.default_model:
            return None
        return self.build(self._config.default_model)

    def list_model_ids(self) -> list[str]:
        """Return all model IDs from the config."""
        return [m.id for m in self._config.models]

    def list_entries(self) -> list[ModelEntry]:
        """Return all model entries sorted by descending priority."""
        return sorted(self._config.models, key=lambda m: -m.priority)

    def find_entry(self, model_id: str) -> ModelEntry | None:
        """Return the ``ModelEntry`` for *model_id*, or ``None`` if not found."""
        for entry in self._config.models:
            if entry.id == model_id:
                return entry
        return None

    async def aclose(self) -> None:
        """Close the shared HTTP client."""
        await self._http_client.aclose()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_entry(self, model_id: str) -> ModelEntry:
        for entry in self._config.models:
            if entry.id == model_id:
                return entry
        available = [m.id for m in self._config.models]
        raise KeyError(f"Model '{model_id}' not found in YAML config. Available: {available}")

    def _build_from_entry(self, entry: ModelEntry) -> IModelProvider:
        provider_cfg = self._config.providers[entry.provider]
        model_info = _make_model_info(entry)

        ptype = provider_cfg.type

        if ptype == "ollama":
            from citnega.packages.model_gateway.providers.ollama import (
                OllamaProvider,
            )

            return OllamaProvider(
                model_info=model_info,
                base_url=provider_cfg.base_url,
                http_client=self._http_client,
            )

        if ptype in ("openai_compatible", "custom_remote"):
            from citnega.packages.model_gateway.providers.openai_compatible import (
                OpenAICompatibleProvider,
            )

            return OpenAICompatibleProvider(
                model_info=model_info,
                base_url=provider_cfg.base_url,
                api_key=provider_cfg.api_key,
                http_client=self._http_client,
            )

        if ptype == "vllm":
            # vLLM exposes an OpenAI-compatible API
            from citnega.packages.model_gateway.providers.openai_compatible import (
                OpenAICompatibleProvider,
            )

            return OpenAICompatibleProvider(
                model_info=model_info,
                base_url=provider_cfg.base_url,
                api_key=provider_cfg.api_key or "dummy",
                http_client=self._http_client,
            )

        if ptype == "litellm":
            from citnega.packages.model_gateway.providers.litellm_provider import (
                LiteLLMProvider,
            )

            credential = None
            if provider_cfg.pem_file and provider_cfg.auth_mode != "api_key":
                from citnega.packages.model_gateway.auth.pem_auth import build_pem_credential

                credential = build_pem_credential(
                    pem_file=provider_cfg.pem_file,
                    auth_mode=provider_cfg.auth_mode,
                    extra=provider_cfg.extra,
                )

            return LiteLLMProvider(
                model_info=model_info,
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                credential=credential,
                extra_kwargs=provider_cfg.extra,
            )

        raise ValueError(
            f"Unsupported provider type '{ptype}' for model '{entry.id}'. "
            f"Supported: ollama, openai_compatible, vllm, custom_remote, litellm"
        )


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_model_info(entry: ModelEntry) -> ModelInfo:
    # Determine provider type from the config model entry's extra fields or id
    provider_type = entry.provider  # e.g. "ollama_local" — used as display type
    local = "ollama" in provider_type or "lm_studio" in provider_type or "local" in provider_type
    return ModelInfo(
        model_id=entry.id,
        model_name=entry.model_name,
        provider_type=provider_type,
        local=local,
        priority=entry.priority,
        capabilities=ModelCapabilityFlags(),
    )
