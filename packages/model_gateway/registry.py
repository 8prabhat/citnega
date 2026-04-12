"""
ModelRegistry — loads and provides ModelInfo from model_registry.toml.

The registry is the single source of truth for which models are available,
their capabilities, cost rank, and provider type.  It is loaded once at
bootstrap time and consulted by the gateway router on every request.
"""

from __future__ import annotations

from pathlib import Path
import tomllib

from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.protocol.models.model_gateway import ModelCapabilityFlags, ModelInfo
from citnega.packages.shared.errors import ConfigError

_DEFAULT_REGISTRY_TOML = Path(__file__).parent / "model_registry.toml"


class ModelRegistry:
    """
    In-memory registry of available models.

    Loaded from a TOML file with the following structure::

        [[models]]
        model_id      = "gemma3-12b-local"
        provider_type = "ollama"
        model_name    = "gemma3:12b"
        local         = true
        priority      = 90
        preferred_for = ["general", "code"]
        cost_rank     = 1

        [models.capabilities]
        supports_tool_calling  = true
        supports_streaming     = true
        max_context_tokens     = 8192
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}

    def load(self, path: Path | None = None) -> None:
        """Load models from the given TOML file (default: bundled registry)."""
        toml_path = path or _DEFAULT_REGISTRY_TOML
        if not toml_path.exists():
            model_gateway_logger.warning("model_registry_not_found", path=str(toml_path))
            return
        try:
            with open(toml_path, "rb") as fh:
                data = tomllib.load(fh)
        except Exception as exc:
            raise ConfigError(f"Failed to load model registry from {toml_path}: {exc}") from exc

        for entry in data.get("models", []):
            try:
                caps_dict = entry.pop("capabilities", {})
                caps = ModelCapabilityFlags(**caps_dict)
                info = ModelInfo(**entry, capabilities=caps)
                self._models[info.model_id] = info
            except Exception as exc:
                model_gateway_logger.warning(
                    "model_registry_entry_invalid",
                    entry=entry,
                    error=str(exc),
                )

        model_gateway_logger.info(
            "model_registry_loaded",
            count=len(self._models),
            path=str(toml_path),
        )

    def get(self, model_id: str) -> ModelInfo | None:
        return self._models.get(model_id)

    def list_all(self) -> list[ModelInfo]:
        return list(self._models.values())

    def list_by_capability(self, **flags: bool) -> list[ModelInfo]:
        """Filter models matching all given capability flags."""
        result = []
        for info in self._models.values():
            caps = info.capabilities
            if all(getattr(caps, k, None) == v for k, v in flags.items()):
                result.append(info)
        return result

    def update_health(self, model_id: str, status: str) -> None:
        """Update a model's health_status field in-place."""
        if model_id in self._models:
            self._models[model_id] = self._models[model_id].model_copy(
                update={"health_status": status}
            )

    def register(self, info: ModelInfo) -> None:
        """Programmatically register a model (used by tests and bootstrap)."""
        self._models[info.model_id] = info
