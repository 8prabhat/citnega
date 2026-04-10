"""IKeyStore interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IKeyStore(ABC):
    """
    Secret retrieval abstraction.

    Only ModelGateway / IModelProvider implementations call this.
    Keys are held in memory for the duration of a request only.
    """

    @abstractmethod
    def get_key(self, service: str, key_name: str) -> str | None: ...

    @abstractmethod
    def set_key(self, service: str, key_name: str, value: str) -> None: ...

    @abstractmethod
    def delete_key(self, service: str, key_name: str) -> None: ...
