"""Generic framework-translated event."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class GenericFrameworkEvent(BaseEvent):
    """
    Catch-all for framework-native events that have no specific canonical type.

    Adapters emit this when ``translate_event()`` encounters an event type
    they do not know how to map.
    """

    event_type:           str = "GenericFrameworkEvent"
    framework_event_type: str
    payload:              dict[str, object]
