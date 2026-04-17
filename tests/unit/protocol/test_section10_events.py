"""
Section 10 event model tests.

Covers the four event types required by the v6 spec Section 10:
  - RunTerminalReasonEvent  (new)
  - ContextTruncatedEvent   (existing, now exported)
  - RouterDecisionEvent     (existing, now exported)
  - StartupDiagnosticsEvent (new)
"""

from __future__ import annotations

import pytest


class TestRunTerminalReasonEvent:
    def test_basic_construction(self) -> None:
        from citnega.packages.protocol.events.lifecycle import RunTerminalReasonEvent

        ev = RunTerminalReasonEvent(
            session_id="s1",
            run_id="r1",
            reason="completed",
        )
        assert ev.event_type == "RunTerminalReasonEvent"
        assert ev.reason == "completed"
        assert ev.details == ""

    def test_with_details(self) -> None:
        from citnega.packages.protocol.events.lifecycle import RunTerminalReasonEvent

        ev = RunTerminalReasonEvent(
            session_id="s1",
            run_id="r1",
            reason="failed",
            details="connection refused",
        )
        assert ev.details == "connection refused"

    def test_exported_from_protocol_init(self) -> None:
        from citnega.packages.protocol.events import RunTerminalReasonEvent  # noqa: F401

    def test_in_canonical_event_union(self) -> None:
        from citnega.packages.protocol.events import CanonicalEvent, RunTerminalReasonEvent

        ev = RunTerminalReasonEvent(session_id="s", run_id="r", reason="cancelled")
        # isinstance check against union member
        assert isinstance(ev, RunTerminalReasonEvent)
        assert "RunTerminalReasonEvent" in str(CanonicalEvent)

    @pytest.mark.parametrize("reason", ["completed", "cancelled", "failed", "depth_limit", "timeout", "approval_denied"])
    def test_all_reason_codes(self, reason: str) -> None:
        from citnega.packages.protocol.events.lifecycle import RunTerminalReasonEvent

        ev = RunTerminalReasonEvent(session_id="s", run_id="r", reason=reason)
        assert ev.reason == reason

    def test_serialises_to_json(self) -> None:
        import json

        from citnega.packages.protocol.events.lifecycle import RunTerminalReasonEvent

        ev = RunTerminalReasonEvent(session_id="s", run_id="r", reason="completed")
        obj = json.loads(ev.model_dump_json())
        assert obj["event_type"] == "RunTerminalReasonEvent"
        assert obj["reason"] == "completed"


class TestStartupDiagnosticsEvent:
    def test_basic_construction(self) -> None:
        from citnega.packages.protocol.events.diagnostics import StartupDiagnosticsEvent

        ev = StartupDiagnosticsEvent(
            session_id="",
            run_id="",
            checks=["db_connection", "adapter_init"],
            status="passed",
            failures=[],
        )
        assert ev.event_type == "StartupDiagnosticsEvent"
        assert ev.status == "passed"
        assert ev.failures == []
        assert ev.details == {}

    def test_degraded_status_with_failures(self) -> None:
        from citnega.packages.protocol.events.diagnostics import StartupDiagnosticsEvent

        ev = StartupDiagnosticsEvent(
            session_id="",
            run_id="",
            checks=["db_connection", "model_gateway"],
            status="degraded",
            failures=["model_gateway"],
            details={"model_gateway": "skipped in test mode"},
        )
        assert ev.status == "degraded"
        assert "model_gateway" in ev.failures
        assert ev.details["model_gateway"] == "skipped in test mode"

    def test_exported_from_protocol_init(self) -> None:
        from citnega.packages.protocol.events import StartupDiagnosticsEvent  # noqa: F401

    def test_in_canonical_event_union(self) -> None:
        from citnega.packages.protocol.events import CanonicalEvent

        assert "StartupDiagnosticsEvent" in str(CanonicalEvent)

    def test_serialises_to_json(self) -> None:
        import json

        from citnega.packages.protocol.events.diagnostics import StartupDiagnosticsEvent

        ev = StartupDiagnosticsEvent(
            session_id="", run_id="", checks=["db"], status="passed", failures=[]
        )
        obj = json.loads(ev.model_dump_json())
        assert obj["event_type"] == "StartupDiagnosticsEvent"
        assert obj["status"] == "passed"


class TestContextTruncatedEventExport:
    """Verify ContextTruncatedEvent is now exported from the top-level __init__."""

    def test_exported(self) -> None:
        from citnega.packages.protocol.events import ContextTruncatedEvent  # noqa: F401

    def test_fields(self) -> None:
        from citnega.packages.protocol.events import ContextTruncatedEvent

        ev = ContextTruncatedEvent(
            session_id="s",
            run_id="r",
            before_tokens=1000,
            after_tokens=800,
            budget_tokens=800,
            dropped_sources=["kb_retrieval"],
        )
        assert ev.before_tokens == 1000
        assert ev.dropped_sources == ["kb_retrieval"]


class TestRouterDecisionEventExport:
    """Verify RouterDecisionEvent is now exported from the top-level __init__."""

    def test_exported(self) -> None:
        from citnega.packages.protocol.events import RouterDecisionEvent  # noqa: F401

    def test_fields(self) -> None:
        from citnega.packages.protocol.events import RouterDecisionEvent

        ev = RouterDecisionEvent(
            session_id="s",
            run_id="r",
            selected_target="research_agent",
            confidence=0.92,
            rationale="user asked for web search",
        )
        assert ev.selected_target == "research_agent"
        assert ev.confidence == pytest.approx(0.92)
        assert ev.fallback is False


class TestRemoteExecutionEventExport:
    """Verify RemoteExecutionEvent is exported and serializable."""

    def test_exported(self) -> None:
        from citnega.packages.protocol.events import RemoteExecutionEvent  # noqa: F401

    def test_fields(self) -> None:
        from citnega.packages.protocol.events import RemoteExecutionEvent

        ev = RemoteExecutionEvent(
            session_id="s",
            run_id="r",
            callable_name="orchestrator_agent",
            callable_type="core",
            phase="dispatch",
            worker_id="remote-worker-1",
            envelope_id="env-1",
            target_callable="qa_agent",
            verification_result="verified",
            details="attempt=1",
        )
        assert ev.phase == "dispatch"
        assert ev.target_callable == "qa_agent"
