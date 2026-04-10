"""BaseRepository[T] — shared CRUD logic for all repositories."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Generic, TypeVar

from citnega.packages.protocol.interfaces.repository import IRepository
from citnega.packages.storage.database import DatabaseFactory

T = TypeVar("T")


class BaseRepository(IRepository[T], Generic[T]):
    """
    Concrete base that injects DatabaseFactory.

    Subclasses provide:
      - ``_from_row(row)``   — dict → domain model
      - ``_to_row(entity)``  — domain model → dict
      - ``_table``            — table name string
      - ``_id_field``         — primary key column name
    """

    _table:    str
    _id_field: str

    def __init__(self, db: DatabaseFactory) -> None:
        self._db = db

    @abstractmethod
    def _from_row(self, row: dict[str, Any]) -> T: ...

    @abstractmethod
    def _to_row(self, entity: T) -> dict[str, Any]: ...

    async def get(self, id: str) -> T | None:
        row = await self._db.fetchone(
            f"SELECT * FROM {self._table} WHERE {self._id_field} = ?",
            (id,),
        )
        return self._from_row(row) if row else None

    async def delete(self, id: str) -> None:
        async with self._db.write_lock:
            await self._db.execute(
                f"DELETE FROM {self._table} WHERE {self._id_field} = ?",
                (id,),
            )
