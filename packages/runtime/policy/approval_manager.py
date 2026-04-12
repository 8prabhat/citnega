"""
ApprovalManager — manages pending approval requests.

Approval flow:
  1. PolicyEnforcer calls create_approval() to register a new pending approval.
  2. checks.approval_check() emits ApprovalRequestEvent and calls wait_for_response().
  3. External caller (CLI, TUI) calls resolve() with APPROVED or DENIED.
  4. wait_for_response() returns the resolved Approval.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from citnega.packages.protocol.models.approvals import Approval, ApprovalStatus


class ApprovalNotFoundError(Exception):
    """Raised when resolving an unknown approval_id."""


class ApprovalManager:
    """
    In-memory registry of pending approvals keyed by approval_id.

    Thread/coroutine safe via per-approval asyncio.Event.
    """

    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def create_approval(
        self,
        approval_id: str,
        run_id: str,
        callable_name: str,
        input_summary: str,
    ) -> Approval:
        """Register a new PENDING approval and return it."""
        approval = Approval(
            approval_id=approval_id,
            run_id=run_id,
            callable_name=callable_name,
            input_summary=input_summary,
            requested_at=datetime.now(tz=UTC),
        )
        async with self._lock:
            self._approvals[approval_id] = approval
            self._events[approval_id] = asyncio.Event()
        return approval

    async def wait_for_response(self, approval_id: str) -> Approval:
        """
        Suspend until the approval is resolved.

        Should be wrapped with asyncio.wait_for() by the caller to
        enforce a timeout (see checks.approval_check).
        """
        async with self._lock:
            event = self._events.get(approval_id)
        if event is None:
            raise ApprovalNotFoundError(approval_id)
        await event.wait()
        async with self._lock:
            # If cleanup() removed the approval while we waited, return None
            return self._approvals.get(approval_id)  # type: ignore[return-value]

    async def resolve(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        user_note: str | None = None,
    ) -> Approval:
        """
        Resolve a pending approval with APPROVED or DENIED.

        Raises ApprovalNotFoundError if approval_id is unknown.
        Raises ValueError if the approval is not in PENDING state.
        """
        async with self._lock:
            approval = self._approvals.get(approval_id)
            event = self._events.get(approval_id)

        if approval is None or event is None:
            raise ApprovalNotFoundError(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval {approval_id!r} is already in state {approval.status!r}.")

        resolved = approval.model_copy(
            update={
                "status": status,
                "responded_at": datetime.now(tz=UTC),
                "user_note": user_note,
            }
        )
        async with self._lock:
            self._approvals[approval_id] = resolved
        event.set()
        return resolved

    async def timeout_approval(self, approval_id: str) -> None:
        """Mark a pending approval as TIMEOUT (called by checks on asyncio.TimeoutError)."""
        async with self._lock:
            approval = self._approvals.get(approval_id)
            if approval and approval.status == ApprovalStatus.PENDING:
                self._approvals[approval_id] = approval.model_copy(
                    update={
                        "status": ApprovalStatus.TIMEOUT,
                        "responded_at": datetime.now(tz=UTC),
                    }
                )

    def get_pending(self, run_id: str) -> list[Approval]:
        """Return all PENDING approvals for a given run."""
        return [
            a
            for a in self._approvals.values()
            if a.run_id == run_id and a.status == ApprovalStatus.PENDING
        ]

    def cleanup(self, run_id: str) -> None:
        """Remove all approvals for a completed run."""
        ids_to_remove = [aid for aid, a in self._approvals.items() if a.run_id == run_id]
        for aid in ids_to_remove:
            self._approvals.pop(aid, None)
            ev = self._events.pop(aid, None)
            if ev is not None:
                ev.set()  # unblock any lingering waiters
