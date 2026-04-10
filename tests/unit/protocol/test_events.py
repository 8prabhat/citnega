"""Unit tests for protocol events."""

from __future__ import annotations

from datetime import timezone

import pytest

from citnega.packages.protocol.events import (
    ApprovalRequestEvent,
    ApprovalResponseEvent,
    ApprovalTimeoutEvent,
    BaseEvent,
    CallableEndEvent,
    CallablePolicyEvent,
    CallableStartEvent,
    CheckpointEvent,
    ContextAssembledEvent,
    ErrorEvent,
    GenericFrameworkEvent,
    RateLimitEvent,
    RunCompleteEvent,
    RunStateEvent,
    TokenEvent,
)
from citnega.packages.protocol.models.runs import RunState


class TestBaseEvent:
    def test_auto_event_id(self) -> None:
        ev = TokenEvent(
            session_id="s1", run_id="r1", token="hello"
        )
        assert ev.event_id  # non-empty UUID4

    def test_auto_timestamp(self) -> None:
        ev = TokenEvent(session_id="s1", run_id="r1", token="x")
        assert ev.timestamp.tzinfo is not None

    def test_schema_version(self) -> None:
        ev = TokenEvent(session_id="s1", run_id="r1", token="x")
        assert ev.schema_version == 1

    def test_unique_event_ids(self) -> None:
        ev1 = TokenEvent(session_id="s1", run_id="r1", token="a")
        ev2 = TokenEvent(session_id="s1", run_id="r1", token="b")
        assert ev1.event_id != ev2.event_id


class TestTokenEvent:
    def test_fields(self) -> None:
        ev = TokenEvent(
            session_id="s1", run_id="r1",
            token="hello", is_first=True
        )
        assert ev.event_type == "TokenEvent"
        assert ev.token == "hello"
        assert ev.is_first is True


class TestRunStateEvent:
    def test_transition(self) -> None:
        ev = RunStateEvent(
            session_id="s1", run_id="r1",
            from_state=RunState.PENDING,
            to_state=RunState.CONTEXT_ASSEMBLING,
        )
        assert ev.from_state == RunState.PENDING
        assert ev.to_state == RunState.CONTEXT_ASSEMBLING
        assert ev.event_type == "RunStateEvent"


class TestRunCompleteEvent:
    def test_sentinel(self) -> None:
        ev = RunCompleteEvent(
            session_id="s1", run_id="r1",
            final_state=RunState.COMPLETED,
        )
        assert ev.event_type == "RunCompleteEvent"
        assert ev.final_state == RunState.COMPLETED


class TestApprovalEvents:
    def test_request(self) -> None:
        ev = ApprovalRequestEvent(
            session_id="s1", run_id="r1",
            approval_id="a1",
            callable_name="write_file",
            input_summary="write to /tmp/x",
            preview="first 3 lines...",
        )
        assert ev.event_type == "ApprovalRequestEvent"

    def test_response(self) -> None:
        ev = ApprovalResponseEvent(
            session_id="s1", run_id="r1",
            approval_id="a1",
            approved=True,
        )
        assert ev.approved is True

    def test_timeout(self) -> None:
        ev = ApprovalTimeoutEvent(
            session_id="s1", run_id="r1", approval_id="a1"
        )
        assert ev.event_type == "ApprovalTimeoutEvent"


class TestErrorEvent:
    def test_fields(self) -> None:
        ev = ErrorEvent(
            session_id="s1", run_id="r1",
            error_code="CALLABLE_UNHANDLED",
            message="boom",
        )
        assert ev.event_type == "ErrorEvent"
        assert ev.traceback is None


class TestGenericFrameworkEvent:
    def test_payload(self) -> None:
        ev = GenericFrameworkEvent(
            session_id="s1", run_id="r1",
            framework_event_type="some.event",
            payload={"key": "val"},
        )
        assert ev.payload["key"] == "val"


class TestRateLimitEvent:
    def test_fields(self) -> None:
        ev = RateLimitEvent(
            session_id="s1", run_id="r1",
            provider="ollama",
            wait_seconds=2.5,
        )
        assert ev.wait_seconds == 2.5
