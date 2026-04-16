"""Unit tests for specialist and core agents."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.model_gateway import ModelResponse
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_config() -> SessionConfig:
    return SessionConfig(
        session_id="test-sess",
        name="test",
        framework="stub",
        default_model_id="x",
    )


def _context(with_gateway: bool = True) -> CallContext:
    ctx = CallContext(
        session_id="test-sess",
        run_id="run-1",
        turn_id="turn-1",
        session_config=_session_config(),
    )
    if with_gateway:
        ctx = ctx.model_copy(update={"model_gateway": _mock_gateway()})
    return ctx


def _mock_gateway(response_text: str = "Model response.") -> MagicMock:
    gw = MagicMock()
    gw.generate = AsyncMock(
        return_value=ModelResponse(
            model_id="test",
            content=response_text,
            finish_reason="stop",
            usage={"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        )
    )
    return gw


def _make_specialist(cls, **kwargs):
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    # Allow callers to override individual constructor args
    return cls(
        policy_enforcer=kwargs.pop("policy_enforcer", enforcer),
        event_emitter=kwargs.pop("event_emitter", emitter),
        tracer=kwargs.pop("tracer", tracer),
        **kwargs,
    )


def _make_core_agent(cls, emitter: EventEmitter | None = None):
    if emitter is None:
        emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


# ---------------------------------------------------------------------------
# Specialists — stub model gateway
# ---------------------------------------------------------------------------


class TestSummaryAgent:
    @pytest.mark.asyncio
    async def test_summary_without_tool_uses_model(self) -> None:
        from citnega.packages.agents.specialists.summary_agent import SummaryAgent, SummaryInput

        agent = _make_specialist(SummaryAgent)
        result = await agent.invoke(
            SummaryInput(text="Long text " * 50, style="concise", max_words=50),
            _context(),
        )
        assert result.success
        assert result.output.response == "Model response."

    @pytest.mark.asyncio
    async def test_summary_without_gateway_returns_fallback(self) -> None:
        from citnega.packages.agents.specialists.summary_agent import SummaryAgent, SummaryInput

        agent = _make_specialist(SummaryAgent)
        result = await agent.invoke(
            SummaryInput(text="Text " * 10, max_words=5),
            _context(with_gateway=False),
        )
        assert result.success
        assert result.output.response  # should have some content


class TestResearchAgent:
    @pytest.mark.asyncio
    async def test_research_without_tools_uses_model(self) -> None:
        from citnega.packages.agents.specialists.research_agent import ResearchAgent, ResearchInput

        agent = _make_specialist(ResearchAgent)
        result = await agent.invoke(
            ResearchInput(query="What is Python?"),
            _context(),
        )
        assert result.success


class TestFileAgent:
    @pytest.mark.asyncio
    async def test_file_agent_falls_back_to_model(self, tmp_path) -> None:
        from citnega.packages.agents.specialists.file_agent import FileAgent, FileAgentInput

        # Use a mock enforcer to bypass path policy restrictions in unit tests
        mock_enforcer = AsyncMock()
        mock_enforcer.enforce.return_value = None
        mock_enforcer.check_output_size.return_value = None

        async def _run(callable_obj, coro, context, emitter):
            return await coro

        mock_enforcer.run_with_timeout.side_effect = _run
        agent = _make_specialist(FileAgent, policy_enforcer=mock_enforcer)
        result = await agent.invoke(
            FileAgentInput(task="explain this directory", file_path=str(tmp_path)),
            _context(),
        )
        assert result.success


class TestDataAgent:
    @pytest.mark.asyncio
    async def test_data_agent_without_script(self) -> None:
        from citnega.packages.agents.specialists.data_agent import DataAgent, DataAgentInput

        agent = _make_specialist(DataAgent)
        result = await agent.invoke(
            DataAgentInput(task="analyse this CSV", data="col1,col2\n1,2\n3,4"),
            _context(),
        )
        assert result.success


class TestWritingAgent:
    @pytest.mark.asyncio
    async def test_writing_agent_produces_response(self) -> None:
        from citnega.packages.agents.specialists.writing_agent import (
            WritingAgent,
            WritingAgentInput,
        )

        agent = _make_specialist(WritingAgent)
        result = await agent.invoke(
            WritingAgentInput(task="Write a haiku about Python."),
            _context(),
        )
        assert result.success
        assert result.output.response


class TestQAAgent:
    @pytest.mark.asyncio
    async def test_qa_agent_without_tools_uses_model(self) -> None:
        from citnega.packages.agents.specialists.qa_agent import QAAgent, QAAgentInput

        agent = _make_specialist(QAAgent)
        result = await agent.invoke(
            QAAgentInput(include_repo_map=False, include_quality_gate=False),
            _context(),
        )
        assert result.success
        assert result.output.response == "Model response."

    @pytest.mark.asyncio
    async def test_qa_agent_uses_tools_and_falls_back_without_gateway(self) -> None:
        from citnega.packages.agents.specialists.qa_agent import QAAgent, QAAgentInput
        from citnega.packages.protocol.callables.results import InvokeResult
        from citnega.packages.protocol.callables.types import CallableType
        from citnega.packages.tools.builtin.quality_gate import (
            QualityCheckResult,
            QualityGateOutput,
        )
        from citnega.packages.tools.builtin.repo_map import RepoMapOutput

        repo_tool = MagicMock()
        repo_tool.invoke = AsyncMock(
            return_value=InvokeResult.ok(
                name="repo_map",
                callable_type=CallableType.TOOL,
                output=RepoMapOutput(
                    root_path="/tmp/repo",
                    total_files_scanned=30,
                    python_files_scanned=20,
                    top_modules=["packages:10", "apps:5"],
                    hotspots=["packages/runtime/app_service.py:100 lines"],
                    import_edges=["packages->apps:3"],
                    summary="Scanned 30 files.",
                ),
                duration_ms=10,
            )
        )

        gate_tool = MagicMock()
        gate_tool.invoke = AsyncMock(
            return_value=InvokeResult.ok(
                name="quality_gate",
                callable_type=CallableType.TOOL,
                output=QualityGateOutput(
                    passed=False,
                    profile="quick",
                    working_dir="/tmp/repo",
                    total_checks=2,
                    passed_checks=1,
                    failed_checks=1,
                    checks=[
                        QualityCheckResult(
                            name="ruff",
                            command="ruff check .",
                            return_code=1,
                            passed=False,
                            duration_ms=100,
                            stdout_tail="",
                            stderr_tail="err",
                        ),
                        QualityCheckResult(
                            name="pytest",
                            command="pytest -q",
                            return_code=0,
                            passed=True,
                            duration_ms=100,
                            stdout_tail="ok",
                            stderr_tail="",
                        ),
                    ],
                    summary="Quality gate failed.",
                ),
                duration_ms=10,
            )
        )

        agent = _make_specialist(
            QAAgent,
            tool_registry={"repo_map": repo_tool, "quality_gate": gate_tool},
        )
        result = await agent.invoke(
            QAAgentInput(working_dir="/tmp/repo"),
            _context(with_gateway=False),
        )
        assert result.success
        assert "Model unavailable for synthesis" in result.output.response
        assert "repo_map" in result.output.tool_calls_made
        assert "quality_gate" in result.output.tool_calls_made


# ---------------------------------------------------------------------------
# ConversationAgent routing
# ---------------------------------------------------------------------------


class TestConversationAgent:
    @pytest.mark.asyncio
    async def test_direct_model_response(self) -> None:
        from citnega.packages.agents.core.conversation_agent import (
            ConversationAgent,
            ConversationInput,
        )

        agent = _make_core_agent(ConversationAgent)
        result = await agent.invoke(
            ConversationInput(user_input="Hello, how are you?"),
            _context(),
        )
        assert result.success
        assert result.output.response == "Model response."
        assert result.output.routed_to is None

    @pytest.mark.asyncio
    async def test_routes_via_router_agent(self) -> None:
        """ConversationAgent delegates to RouterAgent when one is wired as a peer."""
        import json
        from unittest.mock import MagicMock

        from citnega.packages.agents.core.conversation_agent import (
            ConversationAgent,
            ConversationInput,
        )
        from citnega.packages.agents.core.router import RouterAgent
        from citnega.packages.agents.specialists.research_agent import ResearchAgent

        # Gateway: first call = router JSON, second call = specialist response
        call_count = 0

        async def _generate(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Router returns: route to research_agent, not complete
                return ModelResponse(
                    model_id="x",
                    content=json.dumps(
                        {"agent": "research_agent", "reason": "web research needed", "is_complete": False}
                    ),
                    finish_reason="stop",
                    usage={},
                )
            # Second router call: is_complete
            if call_count == 2:
                return ModelResponse(
                    model_id="x",
                    content=json.dumps(
                        {"agent": "none", "reason": "done", "is_complete": True}
                    ),
                    finish_reason="stop",
                    usage={},
                )
            # Synthesis
            return ModelResponse(
                model_id="x",
                content="Climate change summary.",
                finish_reason="stop",
                usage={},
            )

        gw = MagicMock()
        gw.generate = _generate

        agent = _make_core_agent(ConversationAgent)
        router = _make_core_agent(RouterAgent)
        specialist = _make_specialist(ResearchAgent)

        # Wire: router sees the specialist, conversation sees router + specialist
        router.register_sub_callable(specialist)
        agent.register_sub_callable(router)
        agent.register_sub_callable(specialist)

        ctx = CallContext(
            session_id="s",
            run_id="r",
            turn_id="t",
            session_config=_session_config(),
            model_gateway=gw,
        )
        result = await agent.invoke(
            ConversationInput(user_input="Please research climate change"),
            ctx,
        )
        assert result.success
        assert result.output.routed_to is not None
        assert "research_agent" in result.output.routed_to

    @pytest.mark.asyncio
    async def test_falls_back_to_direct_without_router(self) -> None:
        """Without a RouterAgent peer, ConversationAgent answers directly."""
        from citnega.packages.agents.core.conversation_agent import (
            ConversationAgent,
            ConversationInput,
        )
        from citnega.packages.agents.specialists.research_agent import ResearchAgent

        agent = _make_core_agent(ConversationAgent)
        # Register a specialist but NO router — agent should still answer directly
        agent.register_sub_callable(_make_specialist(ResearchAgent))

        result = await agent.invoke(
            ConversationInput(user_input="Please research climate change"),
            _context(),
        )
        assert result.success
        # routed_to is None because the supervisor loop never ran (no router peer)
        assert result.output.routed_to is None
        assert result.output.response == "Model response."

    @pytest.mark.asyncio
    async def test_no_gateway_returns_unavailable(self) -> None:
        from citnega.packages.agents.core.conversation_agent import (
            ConversationAgent,
            ConversationInput,
        )

        agent = _make_core_agent(ConversationAgent)
        result = await agent.invoke(
            ConversationInput(user_input="Hi"),
            _context(with_gateway=False),
        )
        assert result.success
        assert "unavailable" in result.output.response


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_planner_without_specialists(self) -> None:
        from citnega.packages.agents.core.planner_agent import PlannerAgent, PlannerInput

        # Mock gateway returns a plan then a synthesis
        gw = MagicMock()
        call_count = 0

        async def _generate(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ModelResponse(
                    model_id="x",
                    content="STEP 1: direct | What is Python?\nDONE",
                    finish_reason="stop",
                    usage={},
                )
            return ModelResponse(
                model_id="x",
                content="Python is a programming language.",
                finish_reason="stop",
                usage={},
            )

        gw.generate = _generate
        ctx = CallContext(
            session_id="s",
            run_id="r",
            turn_id="t",
            session_config=_session_config(),
            model_gateway=gw,
        )
        agent = _make_core_agent(PlannerAgent)
        result = await agent.invoke(PlannerInput(goal="Explain Python"), ctx)
        assert result.success
        assert result.output.response

    @pytest.mark.asyncio
    async def test_planner_no_gateway_returns_unavailable(self) -> None:
        from citnega.packages.agents.core.planner_agent import PlannerAgent, PlannerInput

        agent = _make_core_agent(PlannerAgent)
        result = await agent.invoke(
            PlannerInput(goal="Do something"),
            _context(with_gateway=False),
        )
        assert result.success
        assert "unavailable" in result.output.response


# ---------------------------------------------------------------------------
# FR-AGENT-003: RouterDecisionEvent emission
# ---------------------------------------------------------------------------


def _drain_events(emitter: EventEmitter, run_id: str) -> list:
    """Drain all events currently queued for *run_id*."""
    q = emitter.get_queue(run_id)
    events = []
    while not q.empty():
        try:
            events.append(q.get_nowait())
        except Exception:
            break
    return events


class TestRouterDecisionEvent:
    @pytest.mark.asyncio
    async def test_fallback_no_gateway_emits_event(self) -> None:
        """RouterAgent must emit RouterDecisionEvent even when falling back (no gateway)."""
        from citnega.packages.agents.core.router import RouterAgent, RouterInput
        from citnega.packages.protocol.events.routing import RouterDecisionEvent

        emitter = EventEmitter()
        agent = _make_core_agent(RouterAgent, emitter=emitter)
        ctx = _context(with_gateway=False)
        result = await agent.invoke(RouterInput(user_input="hello"), ctx)

        assert result.success
        all_events = _drain_events(emitter, ctx.run_id)
        decision_events = [e for e in all_events if isinstance(e, RouterDecisionEvent)]
        assert len(decision_events) == 1
        evt = decision_events[0]
        assert evt.selected_target == "conversation_agent"
        assert evt.fallback is True
        assert evt.session_id == ctx.session_id

    @pytest.mark.asyncio
    async def test_model_routing_emits_event(self) -> None:
        """RouterAgent emits RouterDecisionEvent with model-chosen target."""
        import json

        from citnega.packages.agents.core.router import RouterAgent, RouterInput
        from citnega.packages.protocol.events.routing import RouterDecisionEvent

        router_response = json.dumps(
            {"agent": "conversation_agent", "reason": "simple query", "is_complete": False}
        )
        emitter = EventEmitter()
        agent = _make_core_agent(RouterAgent, emitter=emitter)
        ctx = _context(with_gateway=True)
        ctx = ctx.model_copy(update={"model_gateway": _mock_gateway(router_response)})

        result = await agent.invoke(RouterInput(user_input="hello"), ctx)

        assert result.success
        all_events = _drain_events(emitter, ctx.run_id)
        decision_events = [e for e in all_events if isinstance(e, RouterDecisionEvent)]
        assert len(decision_events) == 1
        evt = decision_events[0]
        assert evt.selected_target == "conversation_agent"
        assert evt.rationale == "simple query"
        assert evt.fallback is False

    @pytest.mark.asyncio
    async def test_parse_error_emits_fallback_event(self) -> None:
        """Malformed JSON from model → fallback event emitted."""
        from citnega.packages.agents.core.router import RouterAgent, RouterInput
        from citnega.packages.protocol.events.routing import RouterDecisionEvent

        emitter = EventEmitter()
        agent = _make_core_agent(RouterAgent, emitter=emitter)
        ctx = _context(with_gateway=True)
        ctx = ctx.model_copy(update={"model_gateway": _mock_gateway("not valid json {{")})

        result = await agent.invoke(RouterInput(user_input="test"), ctx)

        assert result.success
        all_events = _drain_events(emitter, ctx.run_id)
        decision_events = [e for e in all_events if isinstance(e, RouterDecisionEvent)]
        assert len(decision_events) == 1
        assert decision_events[0].fallback is True
        assert decision_events[0].selected_target == "conversation_agent"


# ---------------------------------------------------------------------------
# FR-AGENT-001: Hot-reload rewires core agents
# ---------------------------------------------------------------------------


class TestHotReloadRewiring:
    @staticmethod
    def _fake_registered_callable(name: str, callable_type):
        from pydantic import BaseModel

        from citnega.packages.protocol.callables.types import CallablePolicy

        class _In(BaseModel):
            text: str = ""

        class _Out(BaseModel):
            response: str = ""

        class _Fake:
            description = "test callable"
            input_schema = _In
            output_schema = _Out
            policy = CallablePolicy()

            def __init__(self):
                self.name = name
                self.callable_type = callable_type

            async def _execute(self, input_obj, context):
                return _Out(response="ok")

        return _Fake()

    def _make_svc(self, agents: dict, tools: dict):
        """Create a minimal ApplicationService stub with given registries."""
        from unittest.mock import MagicMock

        from citnega.packages.runtime.app_service import ApplicationService
        from citnega.packages.shared.registry import CallableRegistry

        runtime = MagicMock()
        runtime.callable_registry = CallableRegistry()
        emitter = EventEmitter()
        approval_mgr = MagicMock()
        reg = CallableRegistry()
        for name, obj in {**tools, **agents}.items():
            try:
                reg.register(name, obj)
            except Exception:
                pass
        svc = ApplicationService(
            runtime=runtime,
            emitter=emitter,
            approval_manager=approval_mgr,
            callable_registry=reg,
        )
        return svc

    def test_register_tool_updates_tool_registry(self) -> None:
        from citnega.packages.protocol.callables.types import CallableType

        svc = self._make_svc({}, {})
        tool = self._fake_registered_callable("my_tool", CallableType.TOOL)

        svc.register_callable(tool)

        assert "my_tool" in svc._callable_registry.get_tools()

    def test_register_specialist_updates_agent_registry(self) -> None:
        from citnega.packages.protocol.callables.types import CallableType

        svc = self._make_svc({}, {})
        specialist = self._fake_registered_callable("my_specialist", CallableType.SPECIALIST)

        svc.register_callable(specialist)

        assert "my_specialist" in svc._callable_registry.get_agents()

    def test_register_callable_calls_wire_core_agents(self) -> None:
        """After registration, wire_core_agents must be called so router sees the new callable."""
        from unittest.mock import patch

        from citnega.packages.protocol.callables.types import CallableType

        svc = self._make_svc({}, {})
        specialist = self._fake_registered_callable("new_specialist", CallableType.SPECIALIST)

        with patch(
            "citnega.packages.agents.registry.AgentRegistry.wire_core_agents"
        ) as mock_wire:
            svc.register_callable(specialist)
            mock_wire.assert_called_once()

    def test_new_specialist_visible_to_router_after_register(self) -> None:
        """After register_callable(), RouterAgent.list_sub_callables() should include new specialist."""
        from citnega.packages.protocol.callables.types import CallableType

        emitter = EventEmitter()
        mgr = ApprovalManager()
        enforcer = PolicyEnforcer(emitter, mgr)
        tracer = MagicMock(spec=Tracer)
        tracer.record = MagicMock()

        from citnega.packages.agents.core.router import RouterAgent

        router = RouterAgent(enforcer, emitter, tracer)
        agents = {"router_agent": router}
        tools: dict = {}

        svc = self._make_svc(agents, tools)

        # Register a new specialist
        specialist = self._fake_registered_callable(
            "brand_new_specialist",
            CallableType.SPECIALIST,
        )

        # Before registration — router has no sub_callables
        assert not any(c.name == "brand_new_specialist" for c in router.list_sub_callables())

        svc.register_callable(specialist)

        # After registration — router should see the new specialist
        sub_names = {c.name for c in router.list_sub_callables()}
        assert "brand_new_specialist" in sub_names
