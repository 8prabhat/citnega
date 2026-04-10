"""Unit tests for key store implementations."""

from __future__ import annotations

import pytest

from citnega.packages.security.key_store import CompositeKeyStore, EnvVarKeyStore
from tests.fixtures.key_store import InMemoryKeyStore


class TestEnvVarKeyStore:
    def test_set_and_get(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = EnvVarKeyStore()
        store.set_key("openai", "api_key", "test-value")
        assert store.get_key("openai", "api_key") == "test-value"

    def test_missing_returns_none(self) -> None:
        store = EnvVarKeyStore()
        assert store.get_key("nonexistent_service", "key_xyz") is None

    def test_delete_key(self) -> None:
        store = EnvVarKeyStore()
        store.set_key("svc", "k", "v")
        store.delete_key("svc", "k")
        assert store.get_key("svc", "k") is None

    def test_env_var_naming(self) -> None:
        store = EnvVarKeyStore()
        store.set_key("My-Service", "my-key", "secret")
        # Should be stored as CITNEGA_MY_SERVICE_MY_KEY
        assert store.get_key("My-Service", "my-key") == "secret"


class TestInMemoryKeyStore:
    def test_set_and_get(self) -> None:
        store = InMemoryKeyStore()
        store.set_key("svc", "k", "value")
        assert store.get_key("svc", "k") == "value"

    def test_missing(self) -> None:
        store = InMemoryKeyStore()
        assert store.get_key("x", "y") is None

    def test_delete(self) -> None:
        store = InMemoryKeyStore()
        store.set_key("s", "k", "v")
        store.delete_key("s", "k")
        assert store.get_key("s", "k") is None


class TestCompositeKeyStore:
    def test_falls_back_to_second_store(self) -> None:
        primary   = InMemoryKeyStore()
        secondary = InMemoryKeyStore()
        secondary.set_key("svc", "k", "from_secondary")

        composite = CompositeKeyStore([primary, secondary])
        assert composite.get_key("svc", "k") == "from_secondary"

    def test_primary_takes_precedence(self) -> None:
        primary   = InMemoryKeyStore()
        secondary = InMemoryKeyStore()
        primary.set_key("svc", "k", "from_primary")
        secondary.set_key("svc", "k", "from_secondary")

        composite = CompositeKeyStore([primary, secondary])
        assert composite.get_key("svc", "k") == "from_primary"

    def test_returns_none_if_all_miss(self) -> None:
        composite = CompositeKeyStore([InMemoryKeyStore(), InMemoryKeyStore()])
        assert composite.get_key("missing", "key") is None

    def test_set_writes_to_primary(self) -> None:
        primary   = InMemoryKeyStore()
        secondary = InMemoryKeyStore()
        composite = CompositeKeyStore([primary, secondary])
        composite.set_key("svc", "k", "v")
        assert primary.get_key("svc", "k") == "v"
        assert secondary.get_key("svc", "k") is None
