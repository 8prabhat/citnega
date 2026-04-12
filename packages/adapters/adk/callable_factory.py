"""
ADK CallableFactory — wraps Citnega callables as ADK-native objects.

All ``google.adk`` imports are confined to this module.

ADK represents tools as functions with type-annotated signatures.
We create a thin async wrapper that calls the Citnega callable's
``invoke()`` and returns the output as a dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_callable_factory import BaseCallableFactory

if TYPE_CHECKING:
    from citnega.packages.adapters.base.event_translator import EventTranslator
    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.sessions import SessionConfig


class ADKCallableFactory(BaseCallableFactory):
    """
    Produces ADK-compatible tool/agent wrappers.

    The actual ADK SDK is imported lazily inside each method so the
    rest of the codebase never depends on ``google.adk`` being installed.
    """

    def __init__(
        self,
        event_translator: EventTranslator,
        session_config: SessionConfig,
    ) -> None:
        super().__init__(event_translator)
        self._session_config = session_config

    def create_tool(self, callable: IInvocable) -> Any:
        """
        Wrap a Citnega tool as an ADK FunctionTool.

        Returns a dict describing the tool that ADK can register.
        ADK's actual FunctionTool wrapping is deferred to the runner,
        which has a live ADK session object.  Here we return a
        lightweight descriptor that the runner passes to ADK.
        """
        return {
            "type": "citnega_tool",
            "name": callable.name,
            "description": self._build_tool_description(callable),
            "callable": callable,
            "input_schema": callable.input_schema.model_json_schema(),
        }

    def create_specialist(self, callable: IStreamable) -> Any:
        """Wrap a specialist as an ADK sub-agent descriptor."""
        return {
            "type": "citnega_specialist",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def create_core_agent(self, callable: IStreamable) -> Any:
        """Wrap a core agent as an ADK agent descriptor."""
        return {
            "type": "citnega_core_agent",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        """Translate ADK-native events to canonical events."""
        # ADK emits events as dataclass-like objects; we use the generic fallback
        return self._translator.translate(framework_event, "", "", None)
