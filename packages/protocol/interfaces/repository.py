"""IRepository[T] — generic CRUD interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class IRepository(Generic[T], ABC):
    """
    Generic repository interface.

    - ``get()`` returns None for missing entities; never raises.
    - ``save()`` is upsert semantics (insert or replace).
    - ``list()`` accepts keyword filters specific to the entity type.
    """

    @abstractmethod
    async def get(self, id: str) -> T | None: ...

    @abstractmethod
    async def list(self, **filters: object) -> list[T]: ...

    @abstractmethod
    async def save(self, entity: T) -> T: ...

    @abstractmethod
    async def delete(self, id: str) -> None: ...
