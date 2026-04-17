"""
ICallableRegistry — protocol for the unified callable (tool + agent) registry.

Concrete implementation: ``citnega.packages.shared.registry.CallableRegistry``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.types import CallableType


class ICallableRegistry(ABC):
    """Unified, type-safe registry for tools and agents."""

    @abstractmethod
    def register(self, name: str, item: IInvocable, *, overwrite: bool = False) -> None:
        """Register *item* under *name*."""

    @abstractmethod
    def resolve(self, name: str) -> IInvocable:
        """Return the item registered as *name* or raise ``CallableNotFoundError``."""

    @abstractmethod
    def get(self, name: str) -> IInvocable | None:
        """Return the item or ``None`` if not found."""

    @abstractmethod
    def list_all(self) -> list[IInvocable]:
        """Return a snapshot of every registered callable."""

    @abstractmethod
    def list_by_type(self, callable_type: CallableType) -> list[IInvocable]:
        """Return all callables whose ``callable_type`` matches *callable_type*."""

    @abstractmethod
    def get_tools(self) -> dict[str, IInvocable]:
        """Return all TOOL-type callables as a name→instance mapping."""

    @abstractmethod
    def get_agents(self) -> dict[str, IInvocable]:
        """Return all non-TOOL callables (specialists + core) as a name→instance mapping."""

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove *name* from the registry (no-op if absent)."""

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __contains__(self, name: object) -> bool: ...
