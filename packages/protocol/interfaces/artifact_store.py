"""IArtifactStore interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class IArtifactStore(ABC):
    @abstractmethod
    async def put_text(self, path: str, content: str) -> Path: ...

    @abstractmethod
    async def put_json(self, path: str, data: dict[str, object]) -> Path: ...

    @abstractmethod
    async def put_bytes(self, path: str, content: bytes) -> Path: ...

    @abstractmethod
    async def get(self, path: str) -> bytes: ...

    @abstractmethod
    async def exists(self, path: str) -> bool: ...

    @abstractmethod
    async def delete(self, path: str) -> None: ...
