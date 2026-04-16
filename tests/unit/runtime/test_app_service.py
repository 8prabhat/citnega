"""
Unit tests for ApplicationService — the IApplicationService facade.

Tests verify that ApplicationService delegates to CoreRuntime's public API
and IFrameworkRunner's typed methods without accessing private attributes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.protocol.models.approvals import ApprovalStatus
from citnega.packages.protocol.models.runner import ConversationStats
from citnega.packages.protocol.models.runs import RunState, RunSummary, StateSnapshot
from citnega.packages.protocol.models.sessions import Session, SessionConfig
from citnega.packages.runtime.app_service import ApplicationService

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_session(session_id: str = "sess-1", name: str = "test-session") -> Session:
    return Session(
        config=SessionConfig(
            session_id=session_id,
            name=name,
            framework="stub",
            default_model_id="test-model",
        ),
        created_at=datetime.now(tz=UTC),
        last_active_at=datetime.now(tz=UTC),
    )


def _make_run_summary(run_id: str = "run-1", session_id: str = "sess-1") -> RunSummary:
    return RunSummary(
        run_id=run_id,
        session_id=session_id,
        state=RunState.COMPLETED,
        started_at=datetime.now(tz=UTC),
    )


class _MockRunner:
    """Typed mock implementing IFrameworkRunner's public methods."""

    def get_active_model_id(self) -> str | None:
        return "test-model-1"

    def get_mode(self) -> str:
        return "chat"

    def set_plan_phase(self, phase: str | None) -> None:
        self._plan_phase = phase

    async def set_mode(self, mode_name: str) -> None:
        self._mode = mode_name

    async def set_model(self, model_id: str) -> None:
        self._model_id = model_id

    async def set_thinking(self, value: bool | None) -> None:
        self._thinking = value

    def get_thinking(self) -> bool | None:
        return None

    def get_conversation_stats(self) -> ConversationStats:
        return ConversationStats(message_count=5, token_estimate=1200, compaction_count=1)

    def get_messages(self) -> list[dict[str, Any]]:
        return [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

    def get_tool_history(self) -> list[dict[str, Any]]:
        return [{"name": "read_file", "success": True}]

    def get_active_skills(self) -> list[str]:
        return getattr(self, "_skills", [])

    def set_active_skills(self, skill_names: list[str]) -> None:
        self._skills = list(skill_names)

    def get_mental_model_spec(self) -> dict[str, Any] | None:
        return getattr(self, "_mental_model_spec", None)

    def set_mental_model_spec(self, spec: dict[str, Any] | None) -> None:
        self._mental_model_spec = spec

    def get_compiled_plan_metadata(self) -> dict[str, Any]:
        return getattr(self, "_compiled_plan_metadata", {})

    def set_compiled_plan_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._compiled_plan_metadata = dict(metadata or {})

    async def add_tool_call(self, name, input_summary, output_summary, success, callable_type="tool"):
        pass

    async def compact(self, summary: str, *, keep_recent: int = 10) -> int:
        return 3


def _make_service(
    runner: object | None = None,
    session: Session | None = None,
) -> ApplicationService:
    """Build an ApplicationService with mocked runtime dependencies."""
    runtime = MagicMock()
    runtime.get_runner = MagicMock(return_value=runner)
    runtime.adapter = MagicMock()
    runtime.adapter.get_runner = MagicMock(return_value=None)
    runtime.adapter.framework_name = "stub"
    runtime.adapter.set_session_model = AsyncMock()

    # Session management
    runtime.create_session = AsyncMock(return_value=session or _make_session())
    runtime.get_session = AsyncMock(return_value=session or _make_session())
    runtime.list_sessions = AsyncMock(return_value=[_make_session()])
    runtime.delete_session = AsyncMock()
    runtime.save_session = AsyncMock()

    # Run management
    runtime.run_turn = AsyncMock(return_value="run-1")
    runtime.get_run_summary = AsyncMock(return_value=_make_run_summary())
    runtime.list_runs_for_session = AsyncMock(return_value=[_make_run_summary()])
    runtime.pause_run = AsyncMock()
    runtime.resume_run = AsyncMock()
    runtime.cancel_run = AsyncMock()
    runtime.get_state_snapshot = AsyncMock(
        return_value=StateSnapshot(
            session_id="sess-1",
            current_run_id=None,
            active_callable=None,
            run_state=RunState.PENDING,
            context_token_count=0,
            checkpoint_available=False,
            framework_name="stub",
            captured_at=datetime.now(tz=UTC),
        )
    )
    runtime.ensure_runner = AsyncMock()
    runtime.refresh_runners = AsyncMock(return_value={"refreshed": [], "skipped": []})
    runtime.callable_registry = MagicMock()

    emitter = MagicMock()
    approval_manager = MagicMock()
    approval_manager.resolve = AsyncMock()

    svc = ApplicationService(
        runtime=runtime,
        emitter=emitter,
        approval_manager=approval_manager,
    )
    return svc


def _mock_capability(name: str, *, callable_type: CallableType = CallableType.CORE) -> MagicMock:
    mock = MagicMock()
    mock.name = name
    mock.get_metadata.return_value = CallableMetadata(
        name=name,
        description=f"{name} description",
        callable_type=callable_type,
        input_schema_json={"type": "object", "properties": {"task": {"type": "string"}}},
        output_schema_json={"type": "object", "properties": {"response": {"type": "string"}}},
        policy=CallablePolicy(),
    )
    return mock


# ── Session management tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session():
    svc = _make_service()
    config = SessionConfig(session_id="s1", name="test", framework="stub", default_model_id="test-model")
    result = await svc.create_session(config)
    assert result.config.session_id == "sess-1"
    svc._runtime.create_session.assert_awaited_once_with(config)


@pytest.mark.asyncio
async def test_get_session():
    svc = _make_service()
    result = await svc.get_session("sess-1")
    assert result is not None
    assert result.config.session_id == "sess-1"
    svc._runtime.get_session.assert_awaited_once_with("sess-1")


@pytest.mark.asyncio
async def test_get_session_returns_none_on_error():
    svc = _make_service()
    svc._runtime.get_session = AsyncMock(side_effect=Exception("not found"))
    result = await svc.get_session("bad-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_sessions():
    svc = _make_service()
    result = await svc.list_sessions(limit=10)
    assert len(result) == 1
    svc._runtime.list_sessions.assert_awaited_once_with(limit=10)


@pytest.mark.asyncio
async def test_delete_session():
    svc = _make_service()
    await svc.delete_session("sess-1")
    svc._runtime.delete_session.assert_awaited_once_with("sess-1")


# ── Run execution tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_turn():
    svc = _make_service()
    with patch("citnega.packages.config.loaders.load_settings") as mock_ls:
        mock_ls.return_value = MagicMock(
            conversation=MagicMock(auto_compact=False, auto_name_from_first_message=False),
        )
        run_id = await svc.run_turn("sess-1", "Hello")
    assert run_id == "run-1"
    svc._runtime.run_turn.assert_awaited_once_with("sess-1", "Hello")


@pytest.mark.asyncio
async def test_get_run():
    svc = _make_service()
    result = await svc.get_run("run-1")
    assert result is not None
    assert result.run_id == "run-1"


@pytest.mark.asyncio
async def test_list_runs():
    svc = _make_service()
    result = await svc.list_runs("sess-1", limit=10)
    assert len(result) == 1
    svc._runtime.list_runs_for_session.assert_awaited_once_with("sess-1", limit=10)


# ── Run control tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pause_run():
    svc = _make_service()
    await svc.pause_run("run-1")
    svc._runtime.pause_run.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
async def test_resume_run():
    svc = _make_service()
    await svc.resume_run("run-1")
    svc._runtime.resume_run.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
async def test_cancel_run():
    svc = _make_service()
    await svc.cancel_run("run-1")
    svc._runtime.cancel_run.assert_awaited_once_with("run-1")


@pytest.mark.asyncio
async def test_respond_to_approval_approved():
    svc = _make_service()
    await svc.respond_to_approval("appr-1", approved=True, note="ok")
    svc._approval_manager.resolve.assert_awaited_once_with(
        "appr-1", ApprovalStatus.APPROVED, user_note="ok"
    )


@pytest.mark.asyncio
async def test_respond_to_approval_denied():
    svc = _make_service()
    await svc.respond_to_approval("appr-1", approved=False)
    svc._approval_manager.resolve.assert_awaited_once_with(
        "appr-1", ApprovalStatus.DENIED, user_note=None
    )


# ── Introspection tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_state_snapshot():
    svc = _make_service()
    result = await svc.get_state_snapshot("sess-1")
    assert result.session_id == "sess-1"
    svc._runtime.get_state_snapshot.assert_awaited_once_with("sess-1")


# ── Model management tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_session_model():
    svc = _make_service()
    await svc.set_session_model("sess-1", "new-model")
    svc._runtime.adapter.set_session_model.assert_awaited_once_with("sess-1", "new-model")


def test_get_session_model_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    assert svc.get_session_model("sess-1") == "test-model-1"


def test_get_session_model_no_runner():
    svc = _make_service(runner=None)
    assert svc.get_session_model("sess-1") is None


def test_set_session_plan_phase():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    svc.set_session_plan_phase("sess-1", "draft")
    assert runner._plan_phase == "draft"


@pytest.mark.asyncio
async def test_set_session_mode():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    await svc.set_session_mode("sess-1", "plan")
    assert runner._mode == "plan"


def test_get_session_mode_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    assert svc.get_session_mode("sess-1") == "chat"


def test_get_session_mode_no_runner():
    svc = _make_service(runner=None)
    assert svc.get_session_mode("sess-1") == "chat"


@pytest.mark.asyncio
async def test_set_session_thinking():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    await svc.set_session_thinking("sess-1", True)
    assert runner._thinking is True


def test_get_session_thinking_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    assert svc.get_session_thinking("sess-1") is None  # default


def test_get_session_thinking_no_runner():
    svc = _make_service(runner=None)
    assert svc.get_session_thinking("sess-1") is None


# ── Conversation management tests ────────────────────────────────────────────


def test_get_conversation_stats_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    stats = svc.get_conversation_stats("sess-1")
    assert stats["message_count"] == 5
    assert stats["token_estimate"] == 1200
    assert stats["compaction_count"] == 1


def test_get_conversation_stats_no_runner():
    svc = _make_service(runner=None)
    stats = svc.get_conversation_stats("sess-1")
    assert stats == {"message_count": 0, "token_estimate": 0, "compaction_count": 0}


def test_get_conversation_messages_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    msgs = svc.get_conversation_messages("sess-1")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_get_conversation_messages_no_runner():
    svc = _make_service(runner=None)
    msgs = svc.get_conversation_messages("sess-1")
    assert msgs == []


@pytest.mark.asyncio
async def test_record_tool_call():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    await svc.record_tool_call("sess-1", "read_file", "in", "out", True)
    # Should not raise


def test_get_session_tool_history_with_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    history = svc.get_session_tool_history("sess-1")
    assert len(history) == 1
    assert history[0]["name"] == "read_file"


@pytest.mark.asyncio
async def test_compact_conversation():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    with patch("citnega.packages.config.loaders.load_settings") as mock_ls:
        mock_ls.return_value = MagicMock(
            conversation=MagicMock(compact_keep_recent=5, compact_use_model=False)
        )
        result = await svc.compact_conversation("sess-1")
    assert result == 3  # _MockRunner.compact returns 3


@pytest.mark.asyncio
async def test_compact_conversation_no_runner():
    svc = _make_service(runner=None)
    with patch("citnega.packages.config.loaders.load_settings") as mock_ls:
        mock_ls.return_value = MagicMock(
            conversation=MagicMock(compact_keep_recent=5, compact_use_model=False)
        )
        result = await svc.compact_conversation("sess-1")
    assert result == 0


# ── Rename tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rename_session():
    svc = _make_service()
    await svc.rename_session("sess-1", "new-name")
    svc._runtime.save_session.assert_awaited_once()
    saved = svc._runtime.save_session.call_args[0][0]
    assert saved.config.name == "new-name"


@pytest.mark.asyncio
async def test_rename_session_not_found():
    svc = _make_service()
    svc._runtime.get_session = AsyncMock(side_effect=Exception("nope"))
    await svc.rename_session("bad-id", "new-name")  # should not raise


# ── Runner access tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_runner_existing():
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    await svc.ensure_runner("sess-1")
    svc._runtime.ensure_runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_runner_creates():
    svc = _make_service(runner=None)
    await svc.ensure_runner("sess-1")
    svc._runtime.ensure_runner.assert_awaited_once_with("sess-1")


# ── Frameworks and models ────────────────────────────────────────────────────


def test_list_frameworks():
    svc = _make_service()
    result = svc.list_frameworks()
    assert result == ["stub"]


def test_compile_mental_model_persists_to_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)

    spec = svc.compile_mental_model("sess-1", "Ask before risky edits. Use parallel work where safe.")

    assert spec["risk_posture"] == "balanced"
    assert runner.get_mental_model_spec() == spec


def test_set_session_skills_persists_to_runner():
    runner = _MockRunner()
    svc = _make_service(runner=runner)

    svc.set_session_skills("sess-1", ["release", "review"])

    assert svc.get_session_skills("sess-1") == ["release", "review"]


def test_list_capabilities_and_compile_workflow_plan(tmp_path: Path):
    runner = _MockRunner()
    svc = _make_service(runner=runner)
    svc._callable_registry.register("conversation_agent", _mock_capability("conversation_agent"), overwrite=True)
    svc._callable_registry.register("qa_agent", _mock_capability("qa_agent", callable_type=CallableType.SPECIALIST), overwrite=True)

    workfolder = tmp_path / "workfolder"
    (workfolder / "skills" / "release").mkdir(parents=True)
    (workfolder / "workflows").mkdir(parents=True)
    (workfolder / "skills" / "release" / "SKILL.md").write_text(
        "---\nname: release\ndescription: Release skill\n---\nUse it.",
        encoding="utf-8",
    )
    (workfolder / "workflows" / "release.yaml").write_text(
        (
            "name: release\n"
            "description: Release workflow\n"
            "steps:\n"
            "  - step_id: qa\n"
            "    capability_id: qa_agent\n"
            "    task: \"Review {target}\"\n"
        ),
        encoding="utf-8",
    )

    settings = MagicMock()
    settings.workspace.workfolder_path = str(workfolder)
    settings.nextgen.skills_enabled = True
    settings.nextgen.workflows_enabled = True
    settings.nextgen.planning_enabled = True
    with patch("citnega.packages.config.loaders.load_settings", return_value=settings):
        capabilities = svc.list_capabilities()
        plan = svc.compile_plan(
            "sess-1",
            "Release readiness",
            workflow_name="release",
            variables={"target": "repo"},
        )

    capability_ids = {item.capability_id for item in capabilities}
    assert "skill:release" in capability_ids
    assert "workflow_template:release" in capability_ids
    assert plan.generated_from == "workflow:release"
    assert plan.steps[0].task == "Review repo"
    assert runner.get_compiled_plan_metadata()["plan_id"] == plan.plan_id


# ── KB tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_kb_no_store():
    svc = _make_service()
    result = await svc.search_kb("test")
    assert result == []


@pytest.mark.asyncio
async def test_add_kb_item_no_store():
    svc = _make_service()
    with pytest.raises(NotImplementedError):
        await svc.add_kb_item(MagicMock())


@pytest.mark.asyncio
async def test_delete_kb_item_no_store():
    svc = _make_service()
    with pytest.raises(NotImplementedError):
        await svc.delete_kb_item("item-1")


# ── Import/export tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_session_no_store():
    svc = _make_service()
    with pytest.raises(NotImplementedError):
        await svc.export_session("sess-1")


@pytest.mark.asyncio
async def test_import_session_not_implemented():
    svc = _make_service()
    with pytest.raises(NotImplementedError):
        await svc.import_session(Path("/tmp/test.jsonl"))


# ── No private access verification ──────────────────────────────────────────


def test_no_private_runtime_access():
    """Verify that ApplicationService source has no _runtime._ private accesses."""
    import inspect

    source = inspect.getsource(ApplicationService)
    # _runtime.adapter and _runtime.callable_registry are public properties
    private_accesses = [
        line.strip()
        for line in source.splitlines()
        if "_runtime._" in line and not line.strip().startswith("#")
    ]
    assert private_accesses == [], (
        f"ApplicationService still accesses private runtime attrs: {private_accesses}"
    )


def test_no_runner_conv_access():
    """Verify that ApplicationService source has no runner._conv accesses."""
    import inspect

    source = inspect.getsource(ApplicationService)
    conv_accesses = [
        line.strip()
        for line in source.splitlines()
        if "runner._conv" in line or ("._conv." in line
        and not line.strip().startswith("#"))
    ]
    assert conv_accesses == [], (
        f"ApplicationService still accesses runner._conv: {conv_accesses}"
    )
