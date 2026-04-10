"""IModelGateway and IModelProvider interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from citnega.packages.protocol.models.model_gateway import (
    ModelChunk,
    ModelInfo,
    ModelRequest,
    ModelResponse,
)


class IModelGateway(ABC):
    """Routes model requests to the appropriate provider."""

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    async def stream_generate(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelChunk]: ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]: ...

    @abstractmethod
    async def health_check_all(self) -> dict[str, str]: ...


class IModelProvider(ABC):
    """
    Single model provider implementation.

    Each provider (Ollama, OpenAI-compat, vLLM, custom) implements this
    interface. Framework packages must NOT be imported here.
    """

    @property
    @abstractmethod
    def model_info(self) -> ModelInfo: ...

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    @abstractmethod
    async def stream_generate(
        self, request: ModelRequest
    ) -> AsyncIterator[ModelChunk]: ...

    @abstractmethod
    async def health_check(self) -> str:
        """Returns "healthy" | "degraded" | "down"."""
        ...

    @abstractmethod
    def supports(self, capability: str) -> bool: ...

    @abstractmethod
    def count_tokens(self, text: str) -> int: ...
