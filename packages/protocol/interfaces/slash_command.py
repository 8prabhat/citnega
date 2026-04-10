"""ISlashCommand interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any


class ISlashCommand(ABC):
    """One slash command implementation (e.g. /help, /export)."""

    name:      str
    help_text: str

    @abstractmethod
    async def execute(self, args: list[str], app_context: Any) -> None: ...
