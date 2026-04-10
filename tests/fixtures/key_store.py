"""In-memory IKeyStore for tests — no real keyring needed."""

from __future__ import annotations

import pytest

from citnega.packages.protocol.interfaces.key_store import IKeyStore


class InMemoryKeyStore(IKeyStore):
    """Simple dict-backed key store for unit tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_key(self, service: str, key_name: str) -> str | None:
        return self._store.get((service, key_name))

    def set_key(self, service: str, key_name: str, value: str) -> None:
        self._store[(service, key_name)] = value

    def delete_key(self, service: str, key_name: str) -> None:
        self._store.pop((service, key_name), None)


@pytest.fixture
def in_memory_key_store() -> InMemoryKeyStore:
    return InMemoryKeyStore()
