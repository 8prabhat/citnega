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
from citnega.packages.protocol.events.context import ContextAssembledEvent, ContextTruncatedEvent
from citnega.packages.protocol.events.diagnostics import StartupDiagnosticsEvent
from citnega.packages.protocol.events.errors import ErrorEvent
from citnega.packages.protocol.events.generic import GenericFrameworkEvent
from citnega.packages.protocol.events.lifecycle import (
    RunCompleteEvent,
    RunStateEvent,
    RunTerminalReasonEvent,
)
from citnega.packages.protocol.events.planning import (
    CapabilityLoadFailedEvent,
    ExecutionBatchCompletedEvent,
    ExecutionBatchStartedEvent,
    MentalModelCompiledEvent,
    ParallelExecutionConflictEvent,
    PlanCompiledEvent,
    PlanValidatedEvent,
    SkillActivatedEvent,
    WorkflowTemplateExpandedEvent,
)
from citnega.packages.protocol.events.rate_limit import RateLimitEvent
from citnega.packages.protocol.events.remote import RemoteExecutionEvent
from citnega.packages.protocol.events.routing import RouterDecisionEvent
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
    | RunTerminalReasonEvent
    | PlanCompiledEvent
    | PlanValidatedEvent
    | SkillActivatedEvent
    | MentalModelCompiledEvent
    | WorkflowTemplateExpandedEvent
    | ExecutionBatchStartedEvent
    | ExecutionBatchCompletedEvent
    | CapabilityLoadFailedEvent
    | ParallelExecutionConflictEvent
    | ContextAssembledEvent
    | ContextTruncatedEvent
    | CheckpointEvent
    | ErrorEvent
    | RateLimitEvent
    | RemoteExecutionEvent
    | RouterDecisionEvent
    | StartupDiagnosticsEvent
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
    "CapabilityLoadFailedEvent",
    "CheckpointEvent",
    "ContextAssembledEvent",
    "ContextTruncatedEvent",
    "ErrorEvent",
    "ExecutionBatchCompletedEvent",
    "ExecutionBatchStartedEvent",
    "GenericFrameworkEvent",
    "MentalModelCompiledEvent",
    "ParallelExecutionConflictEvent",
    "PlanCompiledEvent",
    "PlanValidatedEvent",
    "RateLimitEvent",
    "RemoteExecutionEvent",
    "RouterDecisionEvent",
    "RunCompleteEvent",
    "RunStateEvent",
    "RunTerminalReasonEvent",
    "SkillActivatedEvent",
    "StartupDiagnosticsEvent",
    "ThinkingEvent",
    "TokenEvent",
    "WorkflowTemplateExpandedEvent",
]
