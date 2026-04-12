"""IDatabase interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IDatabase(ABC):
    """Database lifecycle (open, execute, close)."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def execute(self, sql: str, parameters: tuple[Any, ...] | None = None) -> Any: ...

    @abstractmethod
    async def fetchall(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def fetchone(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None: ...
