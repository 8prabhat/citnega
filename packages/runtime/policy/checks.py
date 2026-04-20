"""
Individual policy check implementations.

Each check is a single coroutine function that raises a CallablePolicyError
subclass on violation, or returns None on pass.

Chain order (enforced by PolicyEnforcer):
  1. DepthLimitCheck
  2. PathCheck
  3. NetworkCheck
  4. TimeoutCheck     (wraps _execute — handled by PolicyEnforcer)
  5. OutputSizeCheck  (post-execution — handled by PolicyEnforcer)
  6. ApprovalCheck
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import TYPE_CHECKING

from citnega.packages.protocol.events.callable import CallablePolicyEvent
from citnega.packages.shared.errors import (
    ApprovalDeniedError,
    ApprovalTimeoutError,
    CallableDepthError,
    NetworkNotAllowedError,
    PathNotAllowedError,
)
from citnega.packages.tools.builtin._tool_base import resolve_file_path as _resolve_file_path

if TYPE_CHECKING:
    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter
    from citnega.packages.runtime.policy.approval_manager import ApprovalManager


async def depth_check(
    callable: IInvocable,
    input: BaseModel,
    context: CallContext,
    emitter: IEventEmitter,
) -> None:
    """Reject if invocation depth exceeds policy.max_depth_allowed."""
    if context.depth > callable.policy.max_depth_allowed:
        _emit_policy_event(
            emitter,
            context,
            "depth",
            "denied",
            f"depth={context.depth} > max={callable.policy.max_depth_allowed}",
        )
        raise CallableDepthError(
            f"Callable '{callable.name}' invoked at depth {context.depth}, "
            f"max allowed is {callable.policy.max_depth_allowed}."
        )
    _emit_policy_event(emitter, context, "depth", "passed")


async def path_check(
    callable: IInvocable,
    input: BaseModel,
    context: CallContext,
    emitter: IEventEmitter,
    path_vars: dict[str, str] | None = None,
) -> None:
    """
    Validate file paths in input against policy.allowed_paths.

    Looks for any field named *_path or *_file in the input model.
    Resolves symlinks and ensures path stays within the allowlist.

    Supported placeholder substitutions in allowed_paths:
      ${SESSION_ID}      — current session id
      ${WORKSPACE_ROOT}  — workspace root from PolicyEnforcer path_vars
      ${APP_HOME}        — application home directory from path_vars
    """
    if not callable.policy.allowed_paths:
        _emit_policy_event(emitter, context, "path", "passed")
        return

    _vars = path_vars or {}

    def _substitute(p: str) -> str:
        p = p.replace("${SESSION_ID}", context.session_id)
        p = p.replace("~", str(pathlib.Path.home()))
        for key, val in _vars.items():
            p = p.replace(f"${{{key}}}", val)
        return p

    # Substitute placeholders and resolve to absolute paths
    allowed = [
        _resolve_file_path(_substitute(p))
        for p in callable.policy.allowed_paths
    ]

    # Extract path values from input
    try:
        data = input.model_dump()
    except Exception:
        _emit_policy_event(emitter, context, "path", "passed")
        return

    path_values = [
        v
        for k, v in data.items()
        if isinstance(v, str) and ("path" in k.lower() or "file" in k.lower())
    ]

    for pv in path_values:
        try:
            resolved = _resolve_file_path(pv)
            if not any(_is_within(resolved, allowed_root) for allowed_root in allowed):
                _emit_policy_event(
                    emitter, context, "path", "denied", f"path={pv!r} not in allowlist"
                )
                raise PathNotAllowedError(
                    f"Path {pv!r} is not within any allowed paths for callable '{callable.name}'."
                )
        except (OSError, ValueError):
            # Path doesn't exist or can't be resolved — allow it through
            # (existence check is the tool's responsibility)
            pass

    _emit_policy_event(emitter, context, "path", "passed")


def _is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


async def network_check(
    callable: IInvocable,
    input: BaseModel,
    context: CallContext,
    emitter: IEventEmitter,
    deny_network: bool = False,
) -> None:
    """Block network access when the runtime policy denies it.

    Raises NetworkNotAllowedError when:
      - deny_network is True (global policy disables all external calls), AND
      - the callable declares network_allowed=True (it needs network).

    Callables with network_allowed=False pass unconditionally — they do not
    make external requests regardless of the global setting.
    """
    needs_network = getattr(callable.policy, "network_allowed", False)
    if deny_network and needs_network:
        _emit_policy_event(
            emitter,
            context,
            "network",
            "denied",
            "network access disabled by runtime policy",
        )
        raise NetworkNotAllowedError(
            f"Callable '{callable.name}' requires network access, "
            "but network is disabled by runtime policy."
        )
    _emit_policy_event(emitter, context, "network", "passed")


async def approval_check(
    callable: IInvocable,
    input: BaseModel,
    context: CallContext,
    emitter: IEventEmitter,
    approval_manager: ApprovalManager,
) -> None:
    """
    If policy.requires_approval is True, pause until the user approves/denies.

    Emits ApprovalRequestEvent, waits for ApprovalResponseEvent or timeout.
    """
    if not callable.policy.requires_approval:
        _emit_policy_event(emitter, context, "approval", "passed")
        return

    import uuid as _uuid

    from citnega.packages.protocol.events.approval import (
        ApprovalRequestEvent,
        ApprovalTimeoutEvent,
    )
    from citnega.packages.protocol.models.approvals import ApprovalStatus

    approval_id = str(_uuid.uuid4())
    input_summary = _summarise_input(input)

    await approval_manager.create_approval(
        approval_id=approval_id,
        run_id=context.run_id,
        callable_name=callable.name,
        input_summary=input_summary,
    )

    emitter.emit(
        ApprovalRequestEvent(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            callable_name=callable.name,
            approval_id=approval_id,
            input_summary=input_summary,
            preview=input_summary[:200],
        )
    )

    timeout = context.session_config.approval_timeout_seconds
    try:
        result_approval = await asyncio.wait_for(
            approval_manager.wait_for_response(approval_id),
            timeout=float(timeout),
        )
    except TimeoutError:
        emitter.emit(
            ApprovalTimeoutEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                approval_id=approval_id,
            )
        )
        _emit_policy_event(emitter, context, "approval", "denied", "timeout")
        raise ApprovalTimeoutError(f"Approval for '{callable.name}' timed out after {timeout}s.")

    if result_approval.status == ApprovalStatus.DENIED:
        _emit_policy_event(emitter, context, "approval", "denied", "user denied")
        raise ApprovalDeniedError(f"User denied approval for '{callable.name}'.")

    _emit_policy_event(emitter, context, "approval", "passed")


def _summarise_input(input: object) -> str:
    try:
        from pydantic import BaseModel as _BM

        if isinstance(input, _BM):
            return input.model_dump_json()[:512]
    except Exception:
        return str(repr(input))[:512]
    return str(repr(input))[:512]


def _emit_policy_event(
    emitter: IEventEmitter,
    context: CallContext,
    check_name: str,
    result: str,
    reason: str | None = None,
) -> None:
    emitter.emit(
        CallablePolicyEvent(
            session_id=context.session_id,
            run_id=context.run_id,
            turn_id=context.turn_id,
            check_name=check_name,
            result=result,
            reason=reason,
        )
    )
