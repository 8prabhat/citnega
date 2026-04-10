"""IRoutingPolicy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.models.model_gateway import TaskNeeds


class IRoutingPolicy(ABC):
    """Selects which callables to invoke for a given user input and task needs."""

    @abstractmethod
    async def select(
        self,
        callables: list[IInvocable],
        needs: TaskNeeds,
        input: str,
    ) -> list[IInvocable]: ...
