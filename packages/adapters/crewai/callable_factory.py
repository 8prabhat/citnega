"""
CrewAI CallableFactory — wraps Citnega callables as CrewAI tools.

All ``crewai`` imports are confined here.

CrewAI represents tools as classes with a ``_run()`` method decorated
with @tool.  We create descriptors here and let the runner finalize them
with a live CallContext.
"""

from __future__ import annotations

from typing import Any

from citnega.packages.adapters.base.base_callable_factory import BaseCallableFactory
from citnega.packages.adapters.base.event_translator import EventTranslator
from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
from citnega.packages.protocol.events import CanonicalEvent


class CrewAICallableFactory(BaseCallableFactory):
    """Produces CrewAI tool/agent descriptors."""

    def create_tool(self, callable: IInvocable) -> Any:
        return {
            "type": "citnega_tool",
            "name": callable.name,
            "description": self._build_tool_description(callable),
            "callable": callable,
            "input_schema": callable.input_schema,
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
