"""Routing observability events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class RouterDecisionEvent(BaseEvent):
    """
    Emitted by RouterAgent after every routing decision.

    Lets event consumers reconstruct why a particular specialist or direct
    conversation path was chosen for a given turn.

    Fields
    ------
    selected_target
        Name of the agent or callable chosen (e.g. ``"research_agent"``).
        ``"conversation_agent"`` means a direct response; ``"none"`` means
        the router declared the task complete.
    confidence
        Optional 0.0–1.0 confidence from the model response.  ``None``
        when the router fell back to heuristics (no model / parse error).
    rationale
        One-sentence reason supplied by the model (or a fallback label).
    is_complete
        True when the router declared the accumulated results sufficient.
    fallback
        True when the decision was made by a fallback rule, not the model.
    """

    event_type: str = "RouterDecisionEvent"
    selected_target: str
    confidence: float | None = None
    rationale: str = ""
    is_complete: bool = False
    fallback: bool = False


class ModeAutoSwitchedEvent(BaseEvent):
    """
    Emitted at the start of a turn when auto-mode detection selects a mode
    that differs from the session's persisted mode.

    This is a per-turn override — the session mode is NOT mutated.
    Consumers (e.g. TUI ContextBar) use this to show the effective mode
    for the current turn.

    Fields
    ------
    from_mode   – The session's persisted mode before the override.
    to_mode     – The mode used for this turn (auto-detected).
    confidence  – Classifier confidence (0–1).
    rationale   – One-sentence reason from the intent classifier.
    is_autonomous – True when the session is autonomous (always switches to "autonomous").
    """

    event_type: str = "ModeAutoSwitchedEvent"
    from_mode: str
    to_mode: str
    confidence: float = 1.0
    rationale: str = ""
    is_autonomous: bool = False
