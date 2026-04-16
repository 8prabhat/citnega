"""ISessionMode — interface for named conversation modes."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ISessionMode(ABC):
    """
    A named conversation mode that decorates the system prompt.

    Modes are stateless singletons.  Callers obtain them from the
    registry in ``packages/protocol/modes.py``; they never
    construct concrete classes directly (DIP).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical name: ``"chat"`` | ``"plan"`` | ``"explore"``."""
        ...

    @property
    @abstractmethod
    def display_label(self) -> str:
        """Short UI label, e.g. ``"[PLAN]"``.  Empty string for default chat."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-sentence description shown in /mode help."""
        ...

    @abstractmethod
    def augment_system_prompt(self, base_prompt: str) -> str:
        """
        Return the full system prompt for this mode.

        Implementations append mode-specific instructions to *base_prompt*.
        The base prompt already contains the assistant persona; do not
        replace it — extend it.
        """
        ...
