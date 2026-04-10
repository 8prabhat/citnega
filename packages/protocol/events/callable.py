"""Callable-level events."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from citnega.packages.protocol.events.base import BaseEvent

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.results import InvokeResult


class CallableStartEvent(BaseEvent):
    """Emitted just before a callable's _execute() is called."""

    event_type:      str = "CallableStartEvent"
    input_summary:   str                  # truncated JSON repr of validated input
    depth:           int
    parent_callable: str | None

    @classmethod
    def from_invocation(
        cls,
        callable_: "IInvocable",
        context: "CallContext",
    ) -> "CallableStartEvent":
        try:
            summary = "<input>"
        except Exception:
            summary = "<unable to summarise>"
        return cls(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            callable_name=callable_.name,
            callable_type=callable_.callable_type,
            input_summary=summary,
            depth=context.depth,
            parent_callable=context.parent_callable,
        )


class CallableEndEvent(BaseEvent):
    """Emitted after a callable finishes (success or error)."""

    event_type:    str = "CallableEndEvent"
    output_summary: str
    duration_ms:   int
    policy_result: str        # "passed" | "denied" | "timeout"
    error_code:    str | None = None

    @classmethod
    def from_result(
        cls,
        result: "InvokeResult",
        context: "CallContext",
    ) -> "CallableEndEvent":
        if result.error is not None:
            policy_result = (
                "denied"
                if result.error.error_code.startswith("POLICY_")
                else "failed"
            )
            error_code = result.error.error_code
        else:
            policy_result = "passed"
            error_code = None

        return cls(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            callable_name=result.callable_name,
            callable_type=result.callable_type,
            output_summary="<output>" if result.output else "<none>",
            duration_ms=result.duration_ms,
            policy_result=policy_result,
            error_code=error_code,
        )


class CallablePolicyEvent(BaseEvent):
    """Emitted by PolicyEnforcer for each policy check result."""

    event_type: str = "CallablePolicyEvent"
    check_name: str       # "timeout" | "path" | "network" | "approval" | "depth"
    result:     str       # "passed" | "denied"
    reason:     str | None = None
