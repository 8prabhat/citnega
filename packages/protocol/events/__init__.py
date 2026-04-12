"""
All canonical events — exported from a single location.

Import pattern::

    from citnega.packages.protocol.events import TokenEvent, RunStateEvent, ...
"""

from citnega.packages.protocol.events.approval import (
    ApprovalRequestEvent,
    ApprovalResponseEvent,
    ApprovalTimeoutEvent,
)
from citnega.packages.protocol.events.base import BaseEvent
from citnega.packages.protocol.events.callable import (
    CallableEndEvent,
    CallablePolicyEvent,
    CallableStartEvent,
)
from citnega.packages.protocol.events.checkpoint import CheckpointEvent
from citnega.packages.protocol.events.context import ContextAssembledEvent
from citnega.packages.protocol.events.errors import ErrorEvent
from citnega.packages.protocol.events.generic import GenericFrameworkEvent
from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
from citnega.packages.protocol.events.rate_limit import RateLimitEvent
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.events.thinking import ThinkingEvent

# Union type for type-checking
CanonicalEvent = (
    BaseEvent
    | TokenEvent
    | ThinkingEvent
    | CallableStartEvent
    | CallableEndEvent
    | CallablePolicyEvent
    | ApprovalRequestEvent
    | ApprovalResponseEvent
    | ApprovalTimeoutEvent
    | RunStateEvent
    | RunCompleteEvent
    | ContextAssembledEvent
    | CheckpointEvent
    | ErrorEvent
    | RateLimitEvent
    | GenericFrameworkEvent
)

__all__ = [
    "ApprovalRequestEvent",
    "ApprovalResponseEvent",
    "ApprovalTimeoutEvent",
    "BaseEvent",
    "CallableEndEvent",
    "CallablePolicyEvent",
    "CallableStartEvent",
    "CanonicalEvent",
    "CheckpointEvent",
    "ContextAssembledEvent",
    "ErrorEvent",
    "GenericFrameworkEvent",
    "RateLimitEvent",
    "RunCompleteEvent",
    "RunStateEvent",
    "ThinkingEvent",
    "TokenEvent",
]
