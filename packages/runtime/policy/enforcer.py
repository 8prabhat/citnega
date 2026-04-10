"""
PolicyEnforcer — chains all policy checks in the correct order.

Chain order (Section 7 of spec):
  1. DepthLimitCheck   — reject immediately if depth exceeded
  2. PathCheck         — validate file-path fields against allowlist
  3. NetworkCheck      — flag network intent vs. policy
  4. TimeoutCheck      — wraps _execute() at BaseCallable level (not here)
  5. OutputSizeCheck   — post-execution cap (not here — called by BaseCallable)
  6. ApprovalCheck     — block until user approves/denies (or timeout)

Steps 4 and 5 are handled by BaseCallable.invoke() directly because they
need to wrap / inspect the execution result. This class only runs the
pre-execution checks (1–3, 6).
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.interfaces.events import IEventEmitter
from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.checks import (
    approval_check,
    depth_check,
    network_check,
    path_check,
)


class PolicyEnforcer(IPolicyEnforcer):
    """
    Concrete IPolicyEnforcer that runs the pre-execution check chain.

    Inject one instance per runtime session; it is safe to share across
    concurrent run coroutines because all state is in ApprovalManager
    (which uses asyncio locks internally).
    """

    def __init__(
        self,
        emitter: IEventEmitter,
        approval_manager: ApprovalManager,
    ) -> None:
        self._emitter = emitter
        self._approval_manager = approval_manager

    async def enforce(
        self,
        callable: IInvocable,
        input: BaseModel,
        context: CallContext,
    ) -> None:
        """
        Run all pre-execution policy checks in chain order.

        Raises a CallablePolicyError subclass on the first violation.
        Returns None when all checks pass.
        """
        runtime_logger.debug(
            "policy_enforce_start",
            callable_name=callable.name,
            run_id=context.run_id,
            depth=context.depth,
        )

        # 1. Depth limit
        await depth_check(callable, input, context, self._emitter)

        # 2. Path allowlist
        await path_check(callable, input, context, self._emitter)

        # 3. Network intent vs. policy declaration
        await network_check(callable, input, context, self._emitter)

        # 6. Approval gate (runs last so trivial violations are caught first)
        await approval_check(
            callable, input, context, self._emitter, self._approval_manager
        )

        runtime_logger.debug(
            "policy_enforce_passed",
            callable_name=callable.name,
            run_id=context.run_id,
        )

    # ------------------------------------------------------------------
    # Post-execution helpers (called by BaseCallable, not part of enforce())
    # ------------------------------------------------------------------

    @staticmethod
    async def check_output_size(
        callable: IInvocable,
        output_bytes: int,
        context: CallContext,
        emitter: IEventEmitter,
    ) -> None:
        """
        Raise OutputTooLargeError if output_bytes exceeds policy.max_output_bytes.

        Called by BaseCallable *after* _execute() completes so that the
        enforcer does not need to inspect the result object itself.
        """
        from citnega.packages.protocol.events.callable import CallablePolicyEvent
        from citnega.packages.shared.errors import OutputTooLargeError

        limit = callable.policy.max_output_bytes
        if output_bytes > limit:
            emitter.emit(CallablePolicyEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                check_name="output_size",
                result="denied",
                reason=f"output={output_bytes}B > max={limit}B",
            ))
            raise OutputTooLargeError(
                f"Output of '{callable.name}' is {output_bytes:,} bytes, "
                f"exceeding the {limit:,}-byte limit."
            )
        emitter.emit(CallablePolicyEvent(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            check_name="output_size",
            result="passed",
        ))

    @staticmethod
    async def run_with_timeout(
        callable: IInvocable,
        coro: "asyncio.coroutine",  # type: ignore[type-arg]
        context: CallContext,
        emitter: IEventEmitter,
    ) -> object:
        """
        Wrap an awaitable with the callable's policy timeout.

        Raises CallableTimeoutError on expiry.
        Called by BaseCallable around _execute().
        """
        from citnega.packages.protocol.events.callable import CallablePolicyEvent
        from citnega.packages.shared.errors import CallableTimeoutError

        timeout = callable.policy.timeout_seconds
        try:
            result = await asyncio.wait_for(coro, timeout=float(timeout))
        except asyncio.TimeoutError:
            emitter.emit(CallablePolicyEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                check_name="timeout",
                result="denied",
                reason=f"exceeded {timeout}s",
            ))
            raise CallableTimeoutError(
                f"Callable '{callable.name}' exceeded its timeout of {timeout}s."
            )
        emitter.emit(CallablePolicyEvent(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            check_name="timeout",
            result="passed",
        ))
        return result
