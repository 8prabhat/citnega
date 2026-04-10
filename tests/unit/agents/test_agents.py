"""Unit tests for specialist and core agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
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
    gw.generate = AsyncMock(return_value=ModelResponse(
        model_id="test",
        content=response_text,
        finish_reason="stop",
        usage={"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    ))
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


def _make_core_agent(cls):
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
        async def _run(callable_obj, coro, context, emitter):  # noqa: ANN001
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
        from citnega.packages.agents.specialists.writing_agent import WritingAgent, WritingAgentInput
        agent = _make_specialist(WritingAgent)
        result = await agent.invoke(
            WritingAgentInput(task="Write a haiku about Python."),
            _context(),
        )
        assert result.success
        assert result.output.response


# ---------------------------------------------------------------------------
# ConversationAgent routing
# ---------------------------------------------------------------------------

class TestConversationAgent:
    @pytest.mark.asyncio
    async def test_direct_model_response(self) -> None:
        from citnega.packages.agents.core.conversation_agent import ConversationAgent, ConversationInput
        agent = _make_core_agent(ConversationAgent)
        result = await agent.invoke(
            ConversationInput(user_input="Hello, how are you?"),
            _context(),
        )
        assert result.success
        assert result.output.response == "Model response."
        assert result.output.routed_to is None

    @pytest.mark.asyncio
    async def test_routes_to_research_agent(self) -> None:
        from citnega.packages.agents.core.conversation_agent import ConversationAgent, ConversationInput
        from citnega.packages.agents.specialists.research_agent import ResearchAgent

        agent = _make_core_agent(ConversationAgent)
        specialist = _make_specialist(ResearchAgent)
        agent.register_sub_callable(specialist)

        result = await agent.invoke(
            ConversationInput(user_input="Please research climate change"),
            _context(),
        )
        assert result.success
        assert result.output.routed_to == "research_agent"

    @pytest.mark.asyncio
    async def test_routes_to_summary_agent(self) -> None:
        from citnega.packages.agents.core.conversation_agent import ConversationAgent, ConversationInput
        from citnega.packages.agents.specialists.summary_agent import SummaryAgent

        agent = _make_core_agent(ConversationAgent)
        agent.register_sub_callable(_make_specialist(SummaryAgent))

        result = await agent.invoke(
            ConversationInput(user_input="Summarise this text for me: " + "word " * 100),
            _context(),
        )
        assert result.success
        assert result.output.routed_to == "summary_agent"

    @pytest.mark.asyncio
    async def test_no_gateway_returns_unavailable(self) -> None:
        from citnega.packages.agents.core.conversation_agent import ConversationAgent, ConversationInput
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
                    model_id="x", content="STEP 1: direct | What is Python?\nDONE",
                    finish_reason="stop", usage={}
                )
            return ModelResponse(
                model_id="x", content="Python is a programming language.",
                finish_reason="stop", usage={}
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
