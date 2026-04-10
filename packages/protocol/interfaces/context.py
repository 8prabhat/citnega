"""IContextAssembler and IContextHandler interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod

from citnega.packages.protocol.models.context import ContextObject
from citnega.packages.protocol.models.sessions import Session


class IContextHandler(ABC):
    """
    One enrichment step in the Chain-of-Responsibility context pipeline.

    Each handler adds a ContextSource to the ContextObject and returns it.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def enrich(self, context: ContextObject, session: Session) -> ContextObject: ...


class IContextAssembler(ABC):
    """
    Assembles a ContextObject for a turn by running the handler chain.

    Handlers are injected at bootstrap from settings.toml [context].handlers.
    """

    @abstractmethod
    async def assemble(
        self,
        session: Session,
        user_input: str,
        run_id: str,
    ) -> ContextObject: ...
