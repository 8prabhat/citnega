"""Thinking / reasoning token events."""

from __future__ import annotations

from citnega.packages.protocol.events.base import BaseEvent


class ThinkingEvent(BaseEvent):
    """
    Emitted when a model produces internal reasoning tokens.

    Some models (DeepSeek R1, Qwen3-thinking, QwQ, …) output a chain-of-
    thought inside ``<think>…</think>`` blocks before their final response.
    The runtime parses those out and emits them as ``ThinkingEvent`` so
    the TUI can display them separately from the visible response.

    Consumers (e.g. ``EventConsumerWorker``) should render thinking tokens
    in a collapsible widget distinct from the main ``StreamingBlock``.
    """

    event_type: str = "ThinkingEvent"
    token: str
    is_final: bool = False  # True on the last chunk before </think>
