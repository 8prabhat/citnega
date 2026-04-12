"""
EventTranslator — shared helpers for translating framework-native events
to canonical Citnega events.

Each adapter calls ``translate()`` with its own event object.  If no
specific translation exists, a ``GenericFrameworkEvent`` is returned so
the event is never silently dropped.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from citnega.packages.protocol.events import CanonicalEvent, GenericFrameworkEvent

# Type alias: a translator takes a raw framework event and the base
# correlation fields and returns a CanonicalEvent | None.
_TranslatorFn = Callable[[Any, str, str, str | None], CanonicalEvent | None]


class EventTranslator:
    """
    Registry of per-event-type translation functions.

    Adapters register handlers at construction time::

        translator = EventTranslator(framework_name="adk")
        translator.register("adk.events.ModelEvent", my_translate_fn)
        canonical = translator.translate(fw_event, session_id, run_id)
    """

    def __init__(self, framework_name: str) -> None:
        self._framework_name = framework_name
        self._handlers: dict[str, _TranslatorFn] = {}

    def register(self, event_type_name: str, fn: _TranslatorFn) -> None:
        """Register a translation function for a given framework event type name."""
        self._handlers[event_type_name] = fn

    def translate(
        self,
        framework_event: Any,
        session_id: str,
        run_id: str,
        turn_id: str | None = None,
    ) -> CanonicalEvent:
        """
        Translate a framework-native event to a CanonicalEvent.

        Falls back to GenericFrameworkEvent if no specific handler is
        registered for this event type.
        """
        type_name = type(framework_event).__name__
        handler = self._handlers.get(type_name)
        if handler:
            result = handler(framework_event, session_id, run_id, turn_id)
            if result is not None:
                return result

        # Fallback: wrap as a generic event
        payload: dict[str, object] = {}
        try:
            if hasattr(framework_event, "__dict__"):
                payload = {k: str(v) for k, v in framework_event.__dict__.items()}
            elif hasattr(framework_event, "model_dump"):
                payload = framework_event.model_dump()
        except Exception:
            payload = {"raw": str(framework_event)}

        return GenericFrameworkEvent(
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            framework_name=self._framework_name,
            framework_event_type=type_name,
            payload=payload,
        )
