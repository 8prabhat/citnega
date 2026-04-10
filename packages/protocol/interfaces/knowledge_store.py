"""IKnowledgeStore interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from citnega.packages.protocol.models.kb import KBItem, KBSearchResult, KBSourceType


class IKnowledgeStore(ABC):
    @abstractmethod
    async def add_item(self, item: KBItem) -> KBItem: ...

    @abstractmethod
    async def get_item(self, item_id: str) -> KBItem | None: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[KBSearchResult]: ...

    @abstractmethod
    async def delete_item(self, item_id: str) -> None: ...

    @abstractmethod
    async def list_items(
        self,
        tags: list[str] | None = None,
        source_type: KBSourceType | None = None,
        limit: int = 100,
    ) -> list[KBItem]: ...

    @abstractmethod
    async def export_all(self) -> Path: ...
