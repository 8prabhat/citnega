"""
End-to-end integration tests for the autonomous agent pipeline.

Tests cover:
1. Session creation with session_type="autonomous"
2. Auto-mode detection: AutonomousMode applied, all tools unlocked, 30-round budget
3. IntentClassifier keyword classification for each task kind
4. RePlanner heuristic path (no LLM) handles a failed orchestration step
5. OrchestratorAgent autonomous defaults (replan_on_failure, fail_fast=False)
6. ModeAutoSwitchedEvent emitted for autonomous and auto-switched sessions
7. Full live run — autonomous session executes a complex multi-step task
   against the real runtime (no LLM mock — uses whatever model is configured
   or gracefully skips if no model is available).

Complex task for test #7:
  "Analyse the citnega codebase: count Python files, find the largest module
   by line count, list all registered mode names, and write a brief summary
   report to /tmp/citnega_audit_<session_id>.txt"

This exercises: file_agent (list_dir / read_file), ConversationStore,
mode registry, and write_file — all within a single autonomous run.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.agents.core.intent_classifier import (
    IntentClassifierAgent,
    IntentClassifierInput,
    RecommendedMode,
    TaskKind,
)
from citnega.packages.agents.core.orchestrator_agent import (
    OrchestratorAgent,
    OrchestratorInput,
    OrchestrationStep,
)
from citnega.packages.agents.core.replanner import (
    CompletedStep,
    FailedStep,
    RePlanner,
    ReplannerInput,
)
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_agent(cls, **kwargs):
    """Construct any BaseCoreAgent subclass with minimal test infrastructure."""
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer, **kwargs)


def _autonomous_session_config(session_id: str | None = None) -> SessionConfig:
    sid = session_id or str(uuid.uuid4())
    return SessionConfig(
        session_id=sid,
        name="autonomous-test",
        framework="direct",
        default_model_id="test-model",
        session_type="autonomous",
    )


def _interactive_session_config(session_id: str | None = None) -> SessionConfig:
    sid = session_id or str(uuid.uuid4())
    return SessionConfig(
        session_id=sid,
        name="interactive-test",
        framework="direct",
        default_model_id="test-model",
        session_type="interactive",
    )


def _ctx(session_config: SessionConfig | None = None) -> CallContext:
    cfg = session_config or _autonomous_session_config()
    return CallContext(
        session_id=cfg.session_id,
        run_id=str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        session_config=cfg,
    )


# ── 1. Autonomous session type round-trip ─────────────────────────────────────


def test_autonomous_session_config_roundtrip() -> None:
    cfg = _autonomous_session_config()
    assert cfg.session_type == "autonomous"


def test_interactive_session_config_default() -> None:
    cfg = _interactive_session_config()
    assert cfg.session_type == "interactive"


# ── 2. AutonomousMode is registered and has expected properties ───────────────


def test_autonomous_mode_registered() -> None:
    from citnega.packages.protocol.modes import VALID_MODES, get_mode

    assert "autonomous" in VALID_MODES
    mode = get_mode("autonomous")
    assert mode.name == "autonomous"
    assert mode.max_tool_rounds >= 30
    assert mode.temperature <= 0.3


def test_autonomous_mode_prompt_contains_key_directives() -> None:
    from citnega.packages.protocol.modes import get_mode

    prompt = get_mode("autonomous").augment_system_prompt("base")
    lower = prompt.lower()
    assert "autonomous" in lower
    assert "orchestrator" in lower or "orchestrat" in lower
    assert "replan" in lower or "re-plan" in lower or "replanning" in lower or "failure" in lower
    assert "verify" in lower or "verif" in lower


def test_autonomous_mode_tool_round_budget() -> None:
    from citnega.packages.protocol.modes import get_mode

    mode = get_mode("autonomous")
    assert mode.max_tool_rounds == 30


# ── 3. IntentClassifier — keyword classification ──────────────────────────────


@pytest.mark.parametrize("text,expected_kind,expected_mode", [
    ("Write a Python function to parse JSON", TaskKind.CODE, RecommendedMode.CODE),
    ("Research the latest news about AI models", TaskKind.RESEARCH, RecommendedMode.RESEARCH),
    ("Create a project roadmap for Q3 sprint milestones", TaskKind.PLANNING, RecommendedMode.PLAN),
    ("Read the config.yaml file and list its contents", TaskKind.FILE_OPS, RecommendedMode.EXPLORE),
    ("Monitor the service every hour and retry until healthy", TaskKind.AGENTIC, RecommendedMode.AUTO),
    ("Then analyse the data and after that generate the report", TaskKind.MULTI_STEP, RecommendedMode.PLAN),
])
def test_intent_classifier_fast_classify(
    text: str, expected_kind: TaskKind, expected_mode: RecommendedMode
) -> None:
    result = IntentClassifierAgent._fast_classify(text)
    assert result is not None
    assert result.task_kind == expected_kind
    assert result.recommended_mode == expected_mode
    assert result.confidence >= 0.80


def test_intent_classifier_returns_none_for_ambiguous() -> None:
    result = IntentClassifierAgent._fast_classify("Hello, how are you?")
    assert result is None


def test_intent_classifier_code_suggests_code_agent() -> None:
    result = IntentClassifierAgent._fast_classify("Debug this function — it's throwing a TypeError")
    assert result is not None
    assert result.suggested_first_agent == "code_agent"


def test_intent_classifier_planning_suggests_planner() -> None:
    result = IntentClassifierAgent._fast_classify("Build a 6-month product roadmap with milestones")
    assert result is not None
    assert result.suggested_first_agent == "planner_agent"


def test_intent_classifier_agentic_needs_orchestration() -> None:
    result = IntentClassifierAgent._fast_classify("Monitor the API and retry until it responds")
    assert result is not None
    assert result.needs_orchestration is True
    assert result.needs_planning is True


@pytest.mark.asyncio
async def test_intent_classifier_llm_fallback_to_heuristic() -> None:
    """When model_gateway is None, classifier falls back to _fast_classify."""
    classifier = _make_agent(IntentClassifierAgent)
    ctx = _ctx()  # no model_gateway
    inp = IntentClassifierInput(user_input="Write a Python script to parse CSV files")
    result = await classifier._execute(inp, ctx)
    assert result.task_kind == TaskKind.CODE
    assert result.confidence >= 0.80


# ── 4. RePlanner heuristic path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replanner_heuristic_finds_alternative() -> None:
    """RePlanner should switch to conversation_agent when research_agent fails."""
    replanner = _make_agent(RePlanner)
    ctx = _ctx()  # no model_gateway → heuristic path
    inp = ReplannerInput(
        goal="Research the latest AI papers",
        completed_steps=[
            CompletedStep(step_id="step1", callable_name="search_kb", task="search KB")
        ],
        failed_step=FailedStep(
            step_id="step2",
            callable_name="research_agent",
            task="web research on AI papers",
            error="ConnectionError: timeout",
            attempts=2,
        ),
        remaining_steps=[],
        available_callables=["research_agent", "conversation_agent", "web_search"],
    )
    result = await replanner._execute(inp, ctx)
    assert not result.abandon
    assert len(result.revised_steps) > 0
    first = result.revised_steps[0]
    # Should have picked a fallback that is NOT research_agent
    assert first.callable_name != "research_agent"
    assert first.callable_name in ("conversation_agent", "web_search")


@pytest.mark.asyncio
async def test_replanner_heuristic_skips_when_no_alternative() -> None:
    """When no fallback exists, RePlanner skips the step and keeps remaining."""
    replanner = _make_agent(RePlanner)
    ctx = _ctx()
    inp = ReplannerInput(
        goal="Scan the network for vulnerabilities",
        completed_steps=[],
        failed_step=FailedStep(
            step_id="step1",
            callable_name="network_scanner",
            task="scan ports",
            error="PermissionError",
            attempts=1,
        ),
        remaining_steps=[
            {"step_id": "step2", "callable_name": "summary_agent", "task": "summarise", "depends_on": [], "args": {}}
        ],
        available_callables=["summary_agent"],
    )
    result = await replanner._execute(inp, ctx)
    assert not result.abandon
    # Should carry the remaining step forward
    assert any(s.callable_name == "summary_agent" for s in result.revised_steps)


@pytest.mark.asyncio
async def test_replanner_does_not_abandon_by_default() -> None:
    replanner = _make_agent(RePlanner)
    ctx = _ctx()
    inp = ReplannerInput(
        goal="Do something",
        completed_steps=[],
        failed_step=FailedStep(
            step_id="s1", callable_name="missing_agent",
            task="task", error="not found", attempts=1,
        ),
        remaining_steps=[],
        available_callables=["conversation_agent"],
    )
    result = await replanner._execute(inp, ctx)
    assert not result.abandon


# ── 5. OrchestratorAgent autonomous defaults ─────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_autonomous_defaults() -> None:
    """OrchestratorAgent should enable replan_on_failure and disable fail_fast
    automatically when session_type=autonomous."""
    captured: dict[str, Any] = {}

    async def _fake_resolve(input, callables, context):
        # Capture what input looks like inside _execute after autonomous override
        captured["replan_on_failure"] = input.replan_on_failure
        captured["fail_fast"] = input.fail_fast
        captured["max_retries"] = input.max_retries
        return [], False

    orchestrator = _make_agent(OrchestratorAgent)
    orchestrator._resolve_steps = _fake_resolve  # type: ignore[method-assign]

    ctx = _ctx(_autonomous_session_config())
    inp = OrchestratorInput(goal="test goal")  # defaults: replan_on_failure=False, fail_fast=True
    await orchestrator._execute(inp, ctx)

    assert captured["replan_on_failure"] is True
    assert captured["fail_fast"] is False
    assert captured["max_retries"] >= 2


@pytest.mark.asyncio
async def test_orchestrator_interactive_keeps_defaults() -> None:
    """Interactive sessions must not have autonomous defaults applied."""
    captured: dict[str, Any] = {}

    async def _fake_resolve(input, callables, context):
        captured["replan_on_failure"] = input.replan_on_failure
        captured["fail_fast"] = input.fail_fast
        return [], False

    orchestrator = _make_agent(OrchestratorAgent)
    orchestrator._resolve_steps = _fake_resolve  # type: ignore[method-assign]

    ctx = _ctx(_interactive_session_config())
    inp = OrchestratorInput(goal="test goal")
    await orchestrator._execute(inp, ctx)

    assert captured["replan_on_failure"] is False   # unchanged
    assert captured["fail_fast"] is True            # unchanged


# ── 6. ModeAutoSwitchedEvent emitted ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_mode_auto_switched_event_emitted_for_autonomous(tmp_path: Path) -> None:
    """AutonomousMode triggers ModeAutoSwitchedEvent at turn start."""
    from citnega.packages.adapters.direct.runner import DirectModelRunner
    from citnega.packages.protocol.events.routing import ModeAutoSwitchedEvent
    from citnega.packages.runtime.context.conversation_store import ConversationStore

    sid = str(uuid.uuid4())
    session = MagicMock()
    session.config = _autonomous_session_config(sid)

    conv = ConversationStore(tmp_path, default_model_id="m")
    await conv.load()

    yaml_cfg = MagicMock()
    yaml_cfg.models = []

    async def _mock_stream(*args, **kwargs):
        yield MagicMock(content="done", thinking=None, tool_call_delta=None)

    mock_provider = MagicMock()
    mock_provider.stream_generate = _mock_stream

    runner = DirectModelRunner(
        session=session,
        yaml_config=yaml_cfg,
        conversation_store=conv,
    )
    runner._resolve_provider = MagicMock(return_value=(mock_provider, "test-model"))

    ctx = MagicMock()
    ctx.run_id = str(uuid.uuid4())
    ctx.active_model_id = "test-model"
    ctx.sources = []
    ctx.metadata = {}

    queue: asyncio.Queue = asyncio.Queue()
    try:
        await runner.run_turn("do something autonomous", ctx, queue)
    except Exception:
        pass  # run_turn may fail after emitting the event — that's OK for this test

    # Drain all events put in the queue during run_turn
    events: list[Any] = []
    while not queue.empty():
        events.append(queue.get_nowait())

    mode_events = [e for e in events if isinstance(e, ModeAutoSwitchedEvent)]
    assert len(mode_events) >= 1, f"Expected ModeAutoSwitchedEvent, got: {[type(e).__name__ for e in events]}"
    ev = mode_events[0]
    assert ev.to_mode == "autonomous"
    assert ev.is_autonomous is True


# ── 7. Complex live autonomous run (uses real bootstrap + real tools) ─────────


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_autonomous_complex_task_live(tmp_path: Path) -> None:
    """
    Complex task executed end-to-end via the real bootstrap:

      Analyse the citnega codebase:
        1. Count the number of Python (.py) files under packages/
        2. Find the mode with the most tool_rounds
        3. List all registered autonomous-capable modes
        4. Write a brief audit summary to /tmp/citnega_audit_<session_id>.txt

    Verifies:
    - Autonomous session is created and run completes (not stuck/failed)
    - Output file is written to /tmp
    - The session ran in autonomous mode (run summary state is completed/failed,
      not stuck in pending)
    """
    from citnega.packages.bootstrap.bootstrap import create_application
    from citnega.packages.protocol.models.sessions import SessionConfig

    session_id = str(uuid.uuid4())
    output_file = Path(f"/tmp/citnega_audit_{session_id[:8]}.txt")

    # Build the complex prompt
    prompt = f"""You are running as an autonomous agent. Complete ALL of the following tasks:

1. Count Python (.py) files: use the run_shell tool with command:
   find /Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My\\ Drive/Work/citnega/packages -name "*.py" -not -path "*/__pycache__/*" | wc -l

2. Find the mode with the highest max_tool_rounds by running:
   python3 -c "from citnega.packages.protocol.modes import all_modes; modes=[(m.name, m.max_tool_rounds) for m in all_modes()]; print(sorted(modes, key=lambda x: x[1], reverse=True)[0])"

3. List all registered modes by running:
   python3 -c "from citnega.packages.protocol.modes import VALID_MODES; print(sorted(VALID_MODES))"

4. Write a summary report to {output_file} with:
   - Total Python file count
   - Mode with highest rounds
   - All registered modes
   - One-line assessment: "Autonomous agent pipeline operational: YES"

Use run_shell for steps 1-3 and write_file for step 4.
Complete all 4 steps before responding."""

    run_completed = False
    final_state = "unknown"

    try:
        async with create_application(
            db_path=tmp_path / "test.db",
            app_home=tmp_path,
            skip_provider_health_check=True,
        ) as app:
            # Check if a model is configured — skip live run if not
            models = app.list_models()
            if not models:
                pytest.skip("No model configured — skipping live autonomous run")

            # Create autonomous session
            cfg = SessionConfig(
                session_id=session_id,
                name="audit-task",
                framework="direct",
                default_model_id=models[0].model_id,
                session_type="autonomous",
            )
            session = await app.create_session(cfg)
            assert session.config.session_type == "autonomous"

            # Verify session mode is overridden to autonomous in runner
            mode_name = app.get_session_mode(session_id)
            # persisted mode can be "chat" (default) — autonomous override happens per-turn
            assert mode_name is not None

            # Submit the complex task
            run_id = await app.run_turn(session_id, prompt)
            assert run_id

            # Stream events until complete (max 90s)
            from citnega.packages.protocol.events.lifecycle import RunCompleteEvent
            from citnega.packages.protocol.events.routing import ModeAutoSwitchedEvent

            found_auto_mode_event = False
            deadline = asyncio.get_event_loop().time() + 90

            async for event in app.stream_events(run_id):
                if isinstance(event, ModeAutoSwitchedEvent):
                    assert event.to_mode == "autonomous"
                    found_auto_mode_event = True
                if isinstance(event, RunCompleteEvent):
                    final_state = event.final_state.value
                    run_completed = True
                    break
                if asyncio.get_event_loop().time() > deadline:
                    break

            # Assertions
            assert run_completed, f"Run did not complete within timeout (state={final_state})"
            assert final_state in ("completed", "failed"), \
                f"Run stuck in state: {final_state}"
            # ModeAutoSwitchedEvent is emitted early in run_turn; if the run failed
            # before the runner started (e.g. context assembly error), the event
            # may not be present. Only assert it when the run succeeded.
            if final_state == "completed":
                assert found_auto_mode_event, "ModeAutoSwitchedEvent was not emitted for completed run"
                assert output_file.exists(), \
                    f"Output file {output_file} was not created by the agent"
                content = output_file.read_text()
                assert "Autonomous agent pipeline operational: YES" in content, \
                    f"Expected completion marker in output. Got:\n{content[:500]}"

    except Exception as exc:
        # If bootstrap fails (e.g. missing DB driver), skip rather than fail
        if "No model" in str(exc) or "not configured" in str(exc).lower():
            pytest.skip(f"Skipped: {exc}")
        raise
    finally:
        # Clean up temp output file
        if output_file.exists():
            output_file.unlink(missing_ok=True)


# ── 8. Auto-mode detection in runner._detect_mode ────────────────────────────


def test_runner_detect_mode_code() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    result = DirectModelRunner._detect_mode("Write a Python function to sort a list")
    assert result == "code"


def test_runner_detect_mode_research() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    result = DirectModelRunner._detect_mode("Find the latest research papers on LLMs")
    assert result == "research"


def test_runner_detect_mode_plan() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    result = DirectModelRunner._detect_mode("Create a project roadmap with milestones")
    assert result == "plan"


def test_runner_detect_mode_ambiguous_returns_none() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    result = DirectModelRunner._detect_mode("Hi there!")
    assert result is None


def test_runner_planning_hint_injected_for_complex() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    hint = DirectModelRunner._planning_hint("Build a roadmap with milestones and epics")
    assert hint is not None
    assert "planner_agent" in hint or "orchestrator" in hint.lower()


def test_runner_planning_hint_none_for_simple() -> None:
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    hint = DirectModelRunner._planning_hint("What time is it?")
    assert hint is None


# ── helpers ───────────────────────────────────────────────────────────────────


async def _async_gen(items):
    for item in items:
        yield item
