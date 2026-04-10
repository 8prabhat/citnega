"""Unit tests for PolicyEnforcer, ApprovalManager, and individual policy checks."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.protocol.models.approvals import ApprovalStatus
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.policy.approval_manager import ApprovalManager, ApprovalNotFoundError
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.shared.errors import (
    ApprovalDeniedError,
    ApprovalTimeoutError,
    CallableDepthError,
    CallableTimeoutError,
    OutputTooLargeError,
    PathNotAllowedError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_config(**kwargs: object) -> SessionConfig:
    return SessionConfig(
        session_id="sess-1",
        name="test",
        framework="adk",
        default_model_id="model-x",
        **kwargs,  # type: ignore[arg-type]
    )


def _context(depth: int = 0, session_config: SessionConfig | None = None) -> CallContext:
    return CallContext(
        session_id="sess-1",
        run_id="run-1",
        turn_id="turn-1",
        depth=depth,
        session_config=session_config or _session_config(),
    )


def _policy(**kwargs: object) -> CallablePolicy:
    return CallablePolicy(**kwargs)  # type: ignore[arg-type]


def _fake_callable(policy: CallablePolicy, name: str = "fake_tool") -> IInvocable:
    """Return a minimal mock IInvocable."""
    m = MagicMock(spec=IInvocable)
    m.name = name
    m.policy = policy
    return m


# ---------------------------------------------------------------------------
# ApprovalManager
# ---------------------------------------------------------------------------

class TestApprovalManager:
    @pytest.mark.asyncio
    async def test_create_and_resolve_approved(self) -> None:
        mgr = ApprovalManager()
        approval = await mgr.create_approval("a1", "run-1", "tool", "summary")
        assert approval.status == ApprovalStatus.PENDING

        # Resolve in a background task so wait_for_response can proceed
        async def _approve() -> None:
            await asyncio.sleep(0.01)
            await mgr.resolve("a1", ApprovalStatus.APPROVED)

        asyncio.create_task(_approve())
        result = await mgr.wait_for_response("a1")
        assert result.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_resolve_denied(self) -> None:
        mgr = ApprovalManager()
        await mgr.create_approval("a2", "run-1", "tool", "summary")
        asyncio.create_task(_deny_after(mgr, "a2", 0.01))
        result = await mgr.wait_for_response("a2")
        assert result.status == ApprovalStatus.DENIED

    @pytest.mark.asyncio
    async def test_unknown_approval_raises(self) -> None:
        mgr = ApprovalManager()
        with pytest.raises(ApprovalNotFoundError):
            await mgr.wait_for_response("nonexistent")

    @pytest.mark.asyncio
    async def test_double_resolve_raises(self) -> None:
        mgr = ApprovalManager()
        await mgr.create_approval("a3", "run-1", "tool", "summary")
        await mgr.resolve("a3", ApprovalStatus.APPROVED)
        with pytest.raises(ValueError, match="already in state"):
            await mgr.resolve("a3", ApprovalStatus.DENIED)

    @pytest.mark.asyncio
    async def test_cleanup_unblocks_waiters(self) -> None:
        mgr = ApprovalManager()
        await mgr.create_approval("a4", "run-1", "tool", "summary")

        async def _wait() -> None:
            # This should unblock when cleanup() is called
            await mgr.wait_for_response("a4")

        task = asyncio.create_task(_wait())
        await asyncio.sleep(0.01)
        mgr.cleanup("run-1")
        await asyncio.wait_for(task, timeout=1.0)  # should not hang

    @pytest.mark.asyncio
    async def test_get_pending(self) -> None:
        mgr = ApprovalManager()
        await mgr.create_approval("x1", "run-A", "tool", "s")
        await mgr.create_approval("x2", "run-A", "tool", "s")
        await mgr.create_approval("x3", "run-B", "tool", "s")
        pending = mgr.get_pending("run-A")
        assert len(pending) == 2
        assert all(p.run_id == "run-A" for p in pending)


async def _deny_after(mgr: ApprovalManager, aid: str, delay: float) -> None:
    await asyncio.sleep(delay)
    await mgr.resolve(aid, ApprovalStatus.DENIED)


# ---------------------------------------------------------------------------
# depth_check
# ---------------------------------------------------------------------------

class TestDepthCheck:
    @pytest.mark.asyncio
    async def test_within_limit_passes(self) -> None:
        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(max_depth_allowed=3, requires_approval=False))
        ctx = _context(depth=2)
        await enforcer.enforce(callable_, MagicMock(), ctx)  # should not raise

    @pytest.mark.asyncio
    async def test_exceeds_limit_raises(self) -> None:
        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(max_depth_allowed=2, requires_approval=False))
        ctx = _context(depth=3)
        with pytest.raises(CallableDepthError):
            await enforcer.enforce(callable_, MagicMock(), ctx)


# ---------------------------------------------------------------------------
# path_check
# ---------------------------------------------------------------------------

class TestPathCheck:
    @pytest.mark.asyncio
    async def test_no_allowed_paths_passes(self, tmp_path: "pytest.TempDir") -> None:
        from pydantic import BaseModel as BM

        class Input(BM):
            file_path: str = str(tmp_path / "anything.txt")

        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(allowed_paths=[], requires_approval=False))
        await enforcer.enforce(callable_, Input(), _context())

    @pytest.mark.asyncio
    async def test_path_within_allowed_passes(self, tmp_path: "pytest.TempDir") -> None:
        from pydantic import BaseModel as BM

        class Input(BM):
            file_path: str = str(tmp_path / "sub" / "file.txt")

        allowed = str(tmp_path)
        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(allowed_paths=[allowed], requires_approval=False))
        # Path doesn't exist but is under allowed root — should pass (tool checks existence)
        await enforcer.enforce(callable_, Input(), _context())

    @pytest.mark.asyncio
    async def test_path_outside_allowed_raises(self, tmp_path: "pytest.TempDir") -> None:
        import tempfile
        from pydantic import BaseModel as BM

        other = tempfile.mkdtemp()

        class Input(BM):
            file_path: str = other + "/secret.txt"

        # Create the file so it can be resolved
        import pathlib
        pathlib.Path(other + "/secret.txt").touch()

        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(
            allowed_paths=[str(tmp_path)], requires_approval=False
        ))
        with pytest.raises(PathNotAllowedError):
            await enforcer.enforce(callable_, Input(), _context())


# ---------------------------------------------------------------------------
# timeout helpers
# ---------------------------------------------------------------------------

class TestRunWithTimeout:
    @pytest.mark.asyncio
    async def test_completes_within_timeout(self) -> None:
        emitter = EventEmitter()

        async def fast() -> int:
            return 42

        result = await PolicyEnforcer.run_with_timeout(
            _fake_callable(_policy(timeout_seconds=5.0)),
            fast(),
            _context(),
            emitter,
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_exceeds_timeout_raises(self) -> None:
        emitter = EventEmitter()

        async def slow() -> None:
            await asyncio.sleep(10)

        with pytest.raises(CallableTimeoutError):
            await PolicyEnforcer.run_with_timeout(
                _fake_callable(_policy(timeout_seconds=0.05)),
                slow(),
                _context(),
                emitter,
            )


# ---------------------------------------------------------------------------
# output_size check
# ---------------------------------------------------------------------------

class TestCheckOutputSize:
    @pytest.mark.asyncio
    async def test_within_limit_passes(self) -> None:
        emitter = EventEmitter()
        await PolicyEnforcer.check_output_size(
            _fake_callable(_policy(max_output_bytes=1024)),
            100,
            _context(),
            emitter,
        )

    @pytest.mark.asyncio
    async def test_exceeds_limit_raises(self) -> None:
        emitter = EventEmitter()
        with pytest.raises(OutputTooLargeError):
            await PolicyEnforcer.check_output_size(
                _fake_callable(_policy(max_output_bytes=100)),
                200,
                _context(),
                emitter,
            )


# ---------------------------------------------------------------------------
# approval_check (via full enforcer)
# ---------------------------------------------------------------------------

class TestApprovalCheck:
    @pytest.mark.asyncio
    async def test_no_approval_required_passes(self) -> None:
        emitter = EventEmitter()
        enforcer = PolicyEnforcer(emitter, ApprovalManager())
        callable_ = _fake_callable(_policy(requires_approval=False))
        await enforcer.enforce(callable_, MagicMock(), _context())

    @pytest.mark.asyncio
    async def test_approval_granted_passes(self) -> None:
        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        callable_ = _fake_callable(_policy(requires_approval=True))
        ctx = _context(session_config=_session_config(approval_timeout_seconds=5))

        async def _approve_first_pending() -> None:
            # Poll until an approval appears, then resolve it
            for _ in range(50):
                pending = mgr.get_pending("run-1")
                if pending:
                    await mgr.resolve(pending[0].approval_id, ApprovalStatus.APPROVED)
                    return
                await asyncio.sleep(0.02)

        task = asyncio.create_task(_approve_first_pending())
        from unittest.mock import MagicMock as MM
        await enforcer.enforce(callable_, MM(), ctx)
        await task

    @pytest.mark.asyncio
    async def test_approval_denied_raises(self) -> None:
        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        callable_ = _fake_callable(_policy(requires_approval=True))
        ctx = _context(session_config=_session_config(approval_timeout_seconds=5))

        async def _deny_first_pending() -> None:
            for _ in range(50):
                pending = mgr.get_pending("run-1")
                if pending:
                    await mgr.resolve(pending[0].approval_id, ApprovalStatus.DENIED)
                    return
                await asyncio.sleep(0.02)

        asyncio.create_task(_deny_first_pending())
        from unittest.mock import MagicMock as MM
        with pytest.raises(ApprovalDeniedError):
            await enforcer.enforce(callable_, MM(), ctx)

    @pytest.mark.asyncio
    async def test_approval_timeout_raises(self) -> None:
        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        callable_ = _fake_callable(_policy(requires_approval=True))
        ctx = _context(session_config=_session_config(approval_timeout_seconds=0.05))

        from unittest.mock import MagicMock as MM
        with pytest.raises(ApprovalTimeoutError):
            await enforcer.enforce(callable_, MM(), ctx)
