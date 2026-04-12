"""
LangGraph CallableFactory — wraps Citnega callables as LangGraph tools.

All ``langgraph`` / ``langchain_core`` imports are confined here.

LangGraph represents tools as StructuredTool instances (from langchain_core).
We create a thin async wrapper per callable and bind input/output schemas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_callable_factory import BaseCallableFactory

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent


class LangGraphCallableFactory(BaseCallableFactory):
    """Produces LangGraph / LangChain StructuredTool wrappers."""

    def create_tool(self, callable: IInvocable) -> Any:
        """
        Return a LangChain StructuredTool that wraps the Citnega callable.

        The actual ``langchain_core.tools.StructuredTool`` creation is deferred
        to the runner which has a live CallContext.  Here we return a descriptor.
        """
        return {
            "type": "citnega_tool",
            "name": callable.name,
            "description": self._build_tool_description(callable),
            "callable": callable,
            "args_schema": callable.input_schema,
        }

    def create_specialist(self, callable: IStreamable) -> Any:
        return {
            "type": "citnega_specialist",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def create_core_agent(self, callable: IStreamable) -> Any:
        return {
            "type": "citnega_core_agent",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        return self._translator.translate(framework_event, "", "", None)
