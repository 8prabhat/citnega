"""
Unit tests for orchestration improvements introduced in v0.6.1:
- NextgenSettings defaults are True
- ConversationAgent passes prior specialist results to subsequent specialists
- RePlanner is present in AgentRegistry output
- PlannerAgent always uses nextgen path
- Bootstrap continues (no SystemExit) when no provider is healthy
- ConversationAgent uses increased default supervisor rounds
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.protocol.models.model_gateway import ModelResponse
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer


# ── helpers ──────────────────────────────────────────────────────────────────

def _session_config() -> SessionConfig:
    return SessionConfig(
        session_id="test-session",
        name="test",
        framework="direct",
        default_model_id="test-model",
    )


def _context(with_gateway: bool = True) -> CallContext:
    gw = None
    if with_gateway:
        gw = MagicMock()
        gw.generate = AsyncMock(
            return_value=ModelResponse(
                model_id="x", content="Model response.", finish_reason="stop", usage={}
            )
        )
    return CallContext(
        session_id="s",
        run_id="r",
        turn_id="t",
        session_config=_session_config(),
        model_gateway=gw,
    )


def _make_core_agent(cls):
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


# ── NextgenSettings defaults ──────────────────────────────────────────────────


def test_nextgen_settings_planning_enabled_by_default() -> None:
    from citnega.packages.config.settings import NextgenSettings
    s = NextgenSettings()
    assert s.planning_enabled is True


def test_nextgen_settings_execution_enabled_by_default() -> None:
    from citnega.packages.config.settings import NextgenSettings
    s = NextgenSettings()
    assert s.execution_enabled is True


def test_nextgen_settings_workflows_enabled_by_default() -> None:
    from citnega.packages.config.settings import NextgenSettings
    s = NextgenSettings()
    assert s.workflows_enabled is True


def test_nextgen_settings_skills_enabled_by_default() -> None:
    from citnega.packages.config.settings import NextgenSettings
    s = NextgenSettings()
    assert s.skills_enabled is True


def test_context_settings_recent_turns_count_is_10() -> None:
    from citnega.packages.config.settings import ContextSettings
    s = ContextSettings()
    assert s.recent_turns_count == 10


# ── PlannerAgent always uses nextgen ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_execute_calls_nextgen_not_legacy() -> None:
    from citnega.packages.agents.core.planner_agent import (
        PlannerAgent,
        PlannerInput,
        PlannerOutput,
    )

    agent = _make_core_agent(PlannerAgent)
    nextgen_mock = AsyncMock(return_value=PlannerOutput(response="nextgen result"))
    legacy_mock = AsyncMock(return_value=PlannerOutput(response="legacy result"))
    agent._execute_nextgen = nextgen_mock
    agent._execute_legacy = legacy_mock

    result = await agent.invoke(PlannerInput(goal="Test goal"), _context())

    assert result.success
    assert result.output.response == "nextgen result"
    nextgen_mock.assert_awaited_once()
    legacy_mock.assert_not_called()


# ── RePlanner in AgentRegistry ────────────────────────────────────────────────


def _make_registry():
    from citnega.packages.agents.registry import AgentRegistry

    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return AgentRegistry(enforcer=enforcer, emitter=emitter, tracer=tracer, tools={})


def test_replanner_is_in_agent_registry_output() -> None:
    registry = _make_registry()
    agents = registry.build_all()
    assert "replanner" in agents, (
        "RePlanner must be in AgentRegistry so OrchestratorAgent can find it via peers"
    )


def test_replanner_is_wired_as_peer_to_orchestrator() -> None:
    registry = _make_registry()
    agents = registry.build_all()
    orchestrator = agents.get("orchestrator_agent")
    assert orchestrator is not None
    peer_names = {c.name for c in orchestrator.list_sub_callables()}
    assert "replanner" in peer_names, (
        "replanner must be wired as a peer of orchestrator_agent for DI-based replan"
    )


# ── ConversationAgent state propagation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_conversation_agent_passes_prior_results_to_next_specialist() -> None:
    """When two specialists are called in sequence, the second receives the first's output."""
    import json

    from citnega.packages.agents.core.conversation_agent import (
        ConversationAgent,
        ConversationInput,
    )
    from citnega.packages.agents.core.router import RouterAgent
    from citnega.packages.protocol.models.model_gateway import ModelResponse

    call_count = 0
    specialist_inputs_received: list[str] = []

    async def _generate(request):
        nonlocal call_count
        call_count += 1
        msgs = request.messages
        last_user = next((m.content for m in reversed(msgs) if m.role == "user"), "")
        if call_count == 1:
            # Router → route to specialist_a
            return ModelResponse(
                model_id="x",
                content=json.dumps({"agent": "spec_a", "reason": "first", "is_complete": False}),
                finish_reason="stop",
                usage={},
            )
        if call_count == 2:
            # Router → route to specialist_b
            return ModelResponse(
                model_id="x",
                content=json.dumps({"agent": "spec_b", "reason": "second", "is_complete": False}),
                finish_reason="stop",
                usage={},
            )
        if call_count == 3:
            # Router → done
            return ModelResponse(
                model_id="x",
                content=json.dumps({"agent": "none", "reason": "done", "is_complete": True}),
                finish_reason="stop",
                usage={},
            )
        # Synthesis
        return ModelResponse(model_id="x", content="Final answer.", finish_reason="stop", usage={})

    gw = MagicMock()
    gw.generate = _generate

    # Specialist A returns a specific result
    spec_a = MagicMock()
    spec_a.name = "spec_a"
    spec_a.callable_type = CallableType.SPECIALIST
    spec_a.input_schema = MagicMock()
    spec_a.input_schema.model_fields = {"user_input": MagicMock(is_required=lambda: True, annotation=str)}

    spec_a_output = SimpleNamespace(response="Specialist A result")
    spec_a.input_schema.model_validate = lambda d: SimpleNamespace(**d)

    async def _spec_a_invoke(input_obj, ctx):
        return SimpleNamespace(success=True, output=spec_a_output, error=None)
    spec_a.invoke = _spec_a_invoke

    # Specialist B captures what input it received
    spec_b = MagicMock()
    spec_b.name = "spec_b"
    spec_b.callable_type = CallableType.SPECIALIST
    spec_b.input_schema = MagicMock()
    spec_b.input_schema.model_fields = {"user_input": MagicMock(is_required=lambda: True, annotation=str)}

    spec_b_output = SimpleNamespace(response="Specialist B result")

    async def _spec_b_invoke(input_obj, ctx):
        # Capture what text was passed
        for field in ("user_input", "query", "task", "text"):
            val = getattr(input_obj, field, None)
            if val:
                specialist_inputs_received.append(str(val))
                break
        return SimpleNamespace(success=True, output=spec_b_output, error=None)

    spec_b.input_schema.model_validate = lambda d: SimpleNamespace(**d)
    spec_b.invoke = _spec_b_invoke

    agent = _make_core_agent(ConversationAgent)
    router = _make_core_agent(RouterAgent)
    router.register_sub_callable(spec_a)
    router.register_sub_callable(spec_b)
    agent.register_sub_callable(router)
    agent.register_sub_callable(spec_a)
    agent.register_sub_callable(spec_b)

    ctx = CallContext(
        session_id="s",
        run_id="r",
        turn_id="t",
        session_config=_session_config(),
        model_gateway=gw,
    )
    result = await agent.invoke(
        ConversationInput(user_input="Do task X then task Y"),
        ctx,
    )

    assert result.success
    # Specialist B must have received context about Specialist A's result
    assert specialist_inputs_received, "Specialist B was never invoked"
    assert "Specialist A result" in specialist_inputs_received[0], (
        f"Specialist B's input should contain specialist A's output, got: {specialist_inputs_received[0]!r}"
    )


# ── ConversationAgent default rounds ─────────────────────────────────────────


def test_conversation_agent_default_supervisor_rounds_is_6() -> None:
    from citnega.packages.agents.core.conversation_agent import _MAX_SUPERVISOR_ROUNDS_DEFAULT
    assert _MAX_SUPERVISOR_ROUNDS_DEFAULT == 6


# ── Bootstrap: no-provider in local_only mode no longer exits ─────────────────


@pytest.mark.asyncio
async def test_bootstrap_no_provider_returns_gateway_not_exits(tmp_path) -> None:
    from citnega.packages.bootstrap.bootstrap import _build_model_gateway

    settings = SimpleNamespace(runtime=SimpleNamespace(local_only=True))
    emitter = MagicMock()

    with (
        patch("citnega.packages.model_gateway.registry.ModelRegistry.load"),
        patch("citnega.packages.model_gateway.registry.ModelRegistry.list_all", return_value=[]),
    ):
        from citnega.packages.model_gateway.gateway import ModelGateway
        gateway = await _build_model_gateway(settings, emitter)

    assert isinstance(gateway, ModelGateway), (
        "Gateway must be returned even when no providers are healthy — "
        "limited mode should start instead of exiting"
    )


# ── IntentClassifier keyword priority ────────────────────────────────────────


def test_multi_step_fires_before_code_for_compound_requests() -> None:
    """'build X then test it' should classify as MULTI_STEP, not CODE."""
    from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent, TaskKind

    result = IntentClassifierAgent._fast_classify("build the service then test it and deploy")
    assert result is not None
    assert result.task_kind == TaskKind.MULTI_STEP, (
        f"Expected MULTI_STEP but got {result.task_kind} — "
        "multi-step check must fire before CODE check"
    )


def test_multi_step_fires_before_code_for_pipeline_keyword() -> None:
    from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent, TaskKind

    result = IntentClassifierAgent._fast_classify("run the full CI pipeline and then release")
    assert result is not None
    assert result.task_kind == TaskKind.MULTI_STEP


def test_agentic_classification_suggests_orchestrator_agent() -> None:
    from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent, TaskKind

    result = IntentClassifierAgent._fast_classify("monitor the service and retry until healthy")
    assert result is not None
    assert result.task_kind == TaskKind.AGENTIC
    assert result.suggested_first_agent == "orchestrator_agent", (
        f"AGENTIC must suggest orchestrator_agent, got: {result.suggested_first_agent!r}"
    )


def test_multi_step_classification_suggests_planner_agent() -> None:
    from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent, TaskKind

    result = IntentClassifierAgent._fast_classify("write the report then publish it")
    assert result is not None
    assert result.task_kind == TaskKind.MULTI_STEP
    assert result.suggested_first_agent == "planner_agent", (
        f"MULTI_STEP must suggest planner_agent, got: {result.suggested_first_agent!r}"
    )


def test_pure_code_request_still_classifies_as_code() -> None:
    """Requests with no sequencing signals should still route to code_agent."""
    from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent, TaskKind

    result = IntentClassifierAgent._fast_classify("implement a Python function to sort a list")
    assert result is not None
    assert result.task_kind == TaskKind.CODE


# ── PlannerAgent orchestrator delegation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_delegates_to_orchestrator_when_wired() -> None:
    """PlannerAgent._execute_nextgen() calls OrchestratorAgent when it is a peer."""
    from citnega.packages.agents.core.orchestrator_agent import OrchestratorOutput
    from citnega.packages.agents.core.planner_agent import PlannerAgent, PlannerInput

    agent = _make_core_agent(PlannerAgent)

    orch_output = OrchestratorOutput(
        response="Multi-step done.",
        plan=["step1: research_agent", "step2: writer_agent"],
        step_results=[],
        completed_steps=2,
        failed_steps=0,
    )
    orch_mock = MagicMock()
    orch_mock.name = "orchestrator_agent"
    orch_mock.invoke = AsyncMock(
        return_value=SimpleNamespace(success=True, output=orch_output, error=None)
    )
    agent.register_sub_callable(orch_mock)

    result = await agent.invoke(PlannerInput(goal="Research topic then write report"), _context())

    assert result.success
    assert result.output.response == "Multi-step done."
    assert len(result.output.plan_steps) == 2
    orch_mock.invoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_planner_falls_back_to_single_capability_when_no_orchestrator() -> None:
    """Without OrchestratorAgent peer, PlannerAgent uses the single-capability path."""
    from citnega.packages.agents.core.planner_agent import PlannerAgent, PlannerInput

    agent = _make_core_agent(PlannerAgent)
    # No OrchestratorAgent peer registered — should hit _execute_single_capability
    fallback_mock = AsyncMock(return_value=SimpleNamespace(
        response="single cap result", plan_steps=[], step_outputs=[],
    ))
    agent._execute_single_capability = fallback_mock

    await agent.invoke(PlannerInput(goal="Do something simple"), _context())

    fallback_mock.assert_awaited_once()
