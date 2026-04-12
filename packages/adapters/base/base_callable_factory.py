"""
BaseCallableFactory — partial implementation of ICallableFactory.

Subclasses (one per framework) implement the three ``create_*`` methods
to wrap Citnega-native callables in framework-native representations.

Shared helpers:
  - ``_build_tool_description(callable)`` — builds a rich description
    string with input schema hint for the LLM.
  - ``_translate_event(framework_event, ...)`` — wraps EventTranslator.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.interfaces.adapter import ICallableFactory

if TYPE_CHECKING:
    from citnega.packages.adapters.base.event_translator import EventTranslator
    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent


class BaseCallableFactory(ICallableFactory):
    """
    Shared helpers for all framework callable factories.

    Subclasses receive an EventTranslator at construction time.
    """

    def __init__(self, event_translator: EventTranslator) -> None:
        self._translator = event_translator

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _build_tool_description(self, callable: IInvocable) -> str:
        """
        Build a rich tool description for injection into the model prompt.

        Format::
            <name>: <description>
            Input schema: <json-schema-summary>
        """
        schema = callable.input_schema.model_json_schema()
        props = schema.get("properties", {})
        param_lines = []
        for field, meta in props.items():
            ftype = meta.get("type", "any")
            desc = meta.get("description", "")
            param_lines.append(f"  {field} ({ftype}): {desc}")
        params_str = "\n".join(param_lines) if param_lines else "  (no parameters)"
        return f"{callable.name}: {callable.description}\nParameters:\n{params_str}"

    def _translate_event(
        self,
        framework_event: Any,
        session_id: str,
        run_id: str,
        turn_id: str | None = None,
    ) -> CanonicalEvent:
        return self._translator.translate(framework_event, session_id, run_id, turn_id)

    # ------------------------------------------------------------------
    # Abstract factory methods (framework-specific)
    # ------------------------------------------------------------------

    @abstractmethod
    def create_tool(self, callable: IInvocable) -> Any: ...

    @abstractmethod
    def create_specialist(self, callable: IStreamable) -> Any: ...

    @abstractmethod
    def create_core_agent(self, callable: IStreamable) -> Any: ...

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        """
        Default implementation: always translates (never returns None).
        Adapters may override to filter events before emission.
        """
        return self._translator.translate(framework_event, "", "", None)
