"""ITokenCounter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.protocol.models.model_gateway import ModelMessage


class ITokenCounter(ABC):
    @abstractmethod
    def count(self, text: str) -> int: ...

    @abstractmethod
    def count_messages(self, messages: list[ModelMessage]) -> int: ...
