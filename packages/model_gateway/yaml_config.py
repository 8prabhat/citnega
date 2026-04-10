"""
YAML-driven model configuration.

Loads ``models.yaml`` (or a custom path) and exposes:
  - ``ProviderConfig``  — how to connect to a backend
  - ``ModelEntry``      — one model definition
  - ``ModelYAMLConfig`` — the full file
  - ``load_yaml_config(path)`` — loads + env-var-substitutes + validates
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

_HERE = Path(__file__).parent
_DEFAULT_YAML = _HERE / "models.yaml"

# ── Env-var substitution ──────────────────────────────────────────────────────

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _substitute(value: Any) -> Any:
    """Recursively substitute ${VAR:-default} in strings."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            spec = m.group(1)
            if ":-" in spec:
                var, default = spec.split(":-", 1)
                return os.environ.get(var.strip(), default)
            return os.environ.get(spec.strip(), "")
        return _ENV_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _substitute(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(item) for item in value]
    return value


# ── Pydantic models ───────────────────────────────────────────────────────────

ProviderType = Literal["ollama", "openai_compatible", "vllm", "custom_remote"]


class ProviderConfig(BaseModel):
    """Connection details for one backend."""
    type:     ProviderType
    base_url: str
    api_key:  str = ""

    model_config = {"extra": "allow"}


class ModelEntry(BaseModel):
    """One row in the models list."""
    id:                 str
    provider:           str           # key into ModelYAMLConfig.providers
    model_name:         str
    priority:           int = 50
    max_context_tokens: int = 8192
    description:        str = ""
    # Set to True for models that emit <think>…</think> reasoning blocks
    # (DeepSeek R1, Qwen3-thinking, QwQ, etc.)
    thinking:           bool = False

    model_config = {"extra": "allow"}


class ModelYAMLConfig(BaseModel):
    """Root of models.yaml."""
    providers:     dict[str, ProviderConfig]
    models:        list[ModelEntry]
    default_model: str = ""

    @model_validator(mode="after")
    def _check_references(self) -> "ModelYAMLConfig":
        known = set(self.providers)
        for entry in self.models:
            if entry.provider not in known:
                raise ValueError(
                    f"Model '{entry.id}' references unknown provider '{entry.provider}'. "
                    f"Known providers: {sorted(known)}"
                )
        if self.default_model:
            known_ids = {m.id for m in self.models}
            if self.default_model not in known_ids:
                raise ValueError(
                    f"default_model '{self.default_model}' is not in the models list."
                )
        return self


# ── Loader ────────────────────────────────────────────────────────────────────

def load_yaml_config(path: Path | None = None) -> ModelYAMLConfig:
    """
    Load, env-var-substitute, and validate ``models.yaml``.

    Args:
        path: Override the default ``packages/model_gateway/models.yaml``.

    Returns:
        A validated ``ModelYAMLConfig``.

    Raises:
        FileNotFoundError: if the YAML file does not exist.
        ValidationError:   if the file fails Pydantic validation.
    """
    resolved = path or _DEFAULT_YAML
    if not resolved.exists():
        raise FileNotFoundError(f"Model config not found: {resolved}")

    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    substituted = _substitute(raw)
    return ModelYAMLConfig.model_validate(substituted)
