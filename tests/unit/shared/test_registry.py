"""Unit tests for packages/shared/registry.py."""

from __future__ import annotations

import threading

import pytest

from citnega.packages.shared.errors import CallableNotFoundError
from citnega.packages.shared.registry import BaseRegistry


class TestBaseRegistry:
    def test_register_and_resolve(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.register("key", "value")
        assert reg.resolve("key") == "value"

    def test_resolve_missing_raises(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        with pytest.raises(CallableNotFoundError):
            reg.resolve("nonexistent")

    def test_get_returns_none_for_missing(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        assert reg.get("missing") is None

    def test_duplicate_registration_raises(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.register("key", "v1")
        with pytest.raises(ValueError, match="already registered"):
            reg.register("key", "v2")

    def test_overwrite_allowed(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.register("key", "v1")
        reg.register("key", "v2", overwrite=True)
        assert reg.resolve("key") == "v2"

    def test_empty_name_raises(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        with pytest.raises(ValueError, match="empty"):
            reg.register("", "value")

    def test_list_all(self) -> None:
        reg: BaseRegistry[int] = BaseRegistry("nums")
        reg.register("a", 1)
        reg.register("b", 2)
        assert set(reg.list_all()) == {1, 2}

    def test_list_names(self) -> None:
        reg: BaseRegistry[int] = BaseRegistry("nums")
        reg.register("x", 10)
        reg.register("y", 20)
        assert set(reg.list_names()) == {"x", "y"}

    def test_unregister(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.register("key", "val")
        reg.unregister("key")
        assert reg.get("key") is None
        assert len(reg) == 0

    def test_unregister_noop_for_missing(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.unregister("nonexistent")  # should not raise

    def test_contains(self) -> None:
        reg: BaseRegistry[str] = BaseRegistry("test")
        reg.register("key", "val")
        assert "key" in reg
        assert "other" not in reg

    def test_len(self) -> None:
        reg: BaseRegistry[int] = BaseRegistry("test")
        assert len(reg) == 0
        reg.register("a", 1)
        assert len(reg) == 1

    def test_thread_safety(self) -> None:
        """Concurrent registrations must not corrupt the registry."""
        reg: BaseRegistry[int] = BaseRegistry("concurrent")
        errors: list[Exception] = []

        def register_many(start: int) -> None:
            for i in range(start, start + 50):
                try:
                    reg.register(f"key_{i}", i)
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=register_many, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(reg) == 200
