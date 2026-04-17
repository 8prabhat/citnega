"""
BaseRegistry[T] — generic, thread-safe registry for named items.

Used by: CallableRegistry, AdapterRegistry, ModelRegistry, SlashCommandRegistry.
All registries share the same register/resolve/list logic (DRY).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Generic, TypeVar

from citnega.packages.shared.errors import CallableNotFoundError

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.types import CallableType

T = TypeVar("T")


class BaseRegistry(Generic[T]):
    """
    Thread-safe, name-keyed registry.

    Items are registered once at bootstrap and resolved at runtime.
    Duplicate registrations raise ``ValueError`` by default to catch
    accidental double-registration early.
    """

    def __init__(self, name: str = "registry") -> None:
        self._name = name
        self._items: dict[str, T] = {}
        self._lock = threading.Lock()

    def register(self, name: str, item: T, *, overwrite: bool = False) -> None:
        """
        Register ``item`` under ``name``.

        Args:
            name: Unique string key.
            item: The item to register.
            overwrite: If True, silently replace an existing entry.
                       If False (default), raise ValueError on collision.

        Raises:
            ValueError: If ``name`` is already registered and ``overwrite`` is False.
        """
        if not name:
            raise ValueError(f"[{self._name}] Registration name must not be empty.")
        with self._lock:
            if name in self._items and not overwrite:
                raise ValueError(
                    f"[{self._name}] '{name}' is already registered. Use overwrite=True to replace."
                )
            self._items[name] = item

    def resolve(self, name: str) -> T:
        """
        Look up an item by name.

        Raises:
            CallableNotFoundError: If no item is registered under ``name``.
        """
        with self._lock:
            if name not in self._items:
                raise CallableNotFoundError(f"[{self._name}] No item registered under '{name}'.")
            return self._items[name]

    def get(self, name: str) -> T | None:
        """Return the item or None if not found (non-raising variant)."""
        with self._lock:
            return self._items.get(name)

    def list_all(self) -> list[T]:
        """Return a snapshot of all registered items."""
        with self._lock:
            return list(self._items.values())

    def list_names(self) -> list[str]:
        """Return a snapshot of all registered names."""
        with self._lock:
            return list(self._items.keys())

    def unregister(self, name: str) -> None:
        """Remove an item. No-op if not registered."""
        with self._lock:
            self._items.pop(name, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._items

    def __repr__(self) -> str:
        with self._lock:
            names = list(self._items.keys())
        return f"{type(self).__name__}(name={self._name!r}, items={names})"


class CallableRegistry(BaseRegistry["IInvocable"]):
    """
    Unified registry for tools *and* agents.

    Extends ``BaseRegistry`` with callable-specific query methods so callers
    can ask for all tools, all agents, or filter by ``CallableType`` without
    duplicating filter logic at every call site.
    """

    def __init__(self) -> None:
        super().__init__(name="callable_registry")

    def list_by_type(self, callable_type: CallableType) -> list[IInvocable]:
        """Return all callables whose ``callable_type`` matches *callable_type*."""
        with self._lock:
            return [
                item
                for item in self._items.values()
                if getattr(item, "callable_type", None) == callable_type
            ]

    def get_tools(self) -> dict[str, IInvocable]:
        """Return all TOOL-type callables as a ``name → instance`` snapshot."""
        from citnega.packages.protocol.callables.types import CallableType as _CT

        with self._lock:
            return {
                name: item
                for name, item in self._items.items()
                if getattr(item, "callable_type", None) == _CT.TOOL
            }

    def get_agents(self) -> dict[str, IInvocable]:
        """Return all non-TOOL callables (specialists + core) as a ``name → instance`` snapshot."""
        from citnega.packages.protocol.callables.types import CallableType as _CT

        with self._lock:
            return {
                name: item
                for name, item in self._items.items()
                if getattr(item, "callable_type", None) != _CT.TOOL
            }
