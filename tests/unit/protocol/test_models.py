"""Unit tests for all protocol Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from citnega.packages.protocol.models import (
    Approval,
    ApprovalStatus,
    CheckpointMeta,
    ContextObject,
    ContextSource,
    KBItem,
    KBSearchResult,
    KBSourceType,
    Message,
    MessageRole,
    ModelCapabilityFlags,
    ModelChunk,
    ModelInfo,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RunState,
    RunSummary,
    Session,
    SessionConfig,
    SessionState,
    StateSnapshot,
    TaskNeeds,
    TERMINAL_RUN_STATES,
    VALID_RUN_TRANSITIONS,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TestSessionModels:
    def test_session_config_defaults(self) -> None:
        cfg = SessionConfig(
            session_id="s1",
            name="My Session",
            framework="adk",
            default_model_id="gemma3",
        )
        assert cfg.local_only is True
        assert cfg.max_callable_depth == 2
        assert cfg.kb_enabled is True
        assert cfg.tags == []

    def test_session_roundtrip(self) -> None:
        cfg = SessionConfig(
            session_id="s1",
            name="Test",
            framework="langgraph",
            default_model_id="gpt-4o",
        )
        session = Session(
            config=cfg,
            created_at=_utcnow(),
            last_active_at=_utcnow(),
        )
        data = session.model_dump()
        restored = Session.model_validate(data)
        assert restored.config.session_id == "s1"
        assert restored.state == SessionState.IDLE

    def test_session_state_enum(self) -> None:
        assert SessionState("idle") == SessionState.IDLE
        assert SessionState("running") == SessionState.RUNNING


class TestRunModels:
    def test_run_state_enum_values(self) -> None:
        assert RunState.PENDING == "pending"
        assert RunState.COMPLETED == "completed"
        assert RunState.CANCELLED == "cancelled"

    def test_terminal_states(self) -> None:
        assert RunState.COMPLETED in TERMINAL_RUN_STATES
        assert RunState.FAILED in TERMINAL_RUN_STATES
        assert RunState.CANCELLED in TERMINAL_RUN_STATES
        assert RunState.EXECUTING not in TERMINAL_RUN_STATES

    def test_valid_transitions_pending(self) -> None:
        allowed = VALID_RUN_TRANSITIONS[RunState.PENDING]
        assert RunState.CONTEXT_ASSEMBLING in allowed
        assert RunState.CANCELLED in allowed
        assert RunState.EXECUTING not in allowed

    def test_run_summary_defaults(self) -> None:
        s = RunSummary(
            run_id="r1",
            session_id="s1",
            started_at=_utcnow(),
            state=RunState.PENDING,
        )
        assert s.turn_count == 0
        assert s.total_tokens == 0
        assert s.error is None

    def test_state_snapshot(self) -> None:
        snap = StateSnapshot(
            session_id="s1",
            current_run_id="r1",
            active_callable=None,
            run_state=RunState.EXECUTING,
            context_token_count=512,
            checkpoint_available=False,
            framework_name="adk",
            captured_at=_utcnow(),
        )
        assert snap.framework_name == "adk"


class TestMessageModels:
    def test_message_roundtrip(self) -> None:
        msg = Message(
            message_id="m1",
            session_id="s1",
            role=MessageRole.USER,
            content="Hello",
            timestamp=_utcnow(),
        )
        data = msg.model_dump()
        restored = Message.model_validate(data)
        assert restored.role == MessageRole.USER
        assert restored.content == "Hello"

    def test_message_role_enum(self) -> None:
        assert MessageRole("user") == MessageRole.USER
        assert MessageRole("assistant") == MessageRole.ASSISTANT


class TestApprovalModels:
    def test_approval_defaults(self) -> None:
        a = Approval(
            approval_id="a1",
            run_id="r1",
            callable_name="write_file",
            input_summary="write to /tmp/x.txt",
            requested_at=_utcnow(),
        )
        assert a.status == ApprovalStatus.PENDING
        assert a.responded_at is None

    def test_approval_status_enum(self) -> None:
        assert ApprovalStatus("approved") == ApprovalStatus.APPROVED
        assert ApprovalStatus("denied") == ApprovalStatus.DENIED


class TestKBModels:
    def test_kb_item_roundtrip(self) -> None:
        item = KBItem(
            item_id="k1",
            title="Climate Report",
            content="Summary content...",
            source_type=KBSourceType.DOCUMENT,
            created_at=_utcnow(),
            updated_at=_utcnow(),
            content_hash="abc123",
        )
        data = item.model_dump()
        restored = KBItem.model_validate(data)
        assert restored.source_type == KBSourceType.DOCUMENT
        assert restored.tags == []


class TestModelGatewayModels:
    def test_model_info_defaults(self) -> None:
        info = ModelInfo(
            model_id="m1",
            provider_type="ollama",
            model_name="gemma3:12b",
            local=True,
            capabilities=ModelCapabilityFlags(),
        )
        assert info.cost_rank == 1
        assert info.health_status == "unknown"

    def test_model_request_defaults(self) -> None:
        req = ModelRequest(messages=[
            ModelMessage(role="user", content="hello")
        ])
        assert req.stream is True
        assert req.temperature == 0.7
        assert req.model_id is None

    def test_task_needs_defaults(self) -> None:
        needs = TaskNeeds()
        assert needs.local_only is False
        assert needs.task_type == "general"


class TestContextModels:
    def test_context_object(self) -> None:
        ctx = ContextObject(
            session_id="s1",
            run_id="r1",
            user_input="hello",
            assembled_at=_utcnow(),
            budget_remaining=8000,
        )
        assert ctx.truncated is False
        assert ctx.sources == []
        assert ctx.total_tokens == 0
