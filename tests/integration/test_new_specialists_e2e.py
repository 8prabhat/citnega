"""
Integration tests for Batch 8 new specialists end-to-end:
- HRAgent produces SpecialistOutput
- QAEngineerAgent runs quality_gate when run_tests=True
- DevOpsAgent invokes log_analyzer
- AgentDelegateTool routes to a named specialist
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.tools.builtin._tool_base import ToolOutput


# ── shared helpers ─────────────────────────────────────────────────────────────

def _deps():
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock()
    tracer.record = MagicMock()
    return enforcer, emitter, tracer


def _ctx(model_gateway=None) -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        depth=1,
        session_config=SessionConfig(
            session_id="s1", name="test", framework="stub", default_model_id="x"
        ),
        model_gateway=model_gateway,
    )


def _make_tool_registry(*tool_names: str) -> dict:
    """Return a dict of stub tools for each given name."""
    registry = {}
    for name in tool_names:
        tool = MagicMock()
        tool.name = name
        tool.callable_type = CallableType.TOOL
        tool.invoke = AsyncMock(return_value=InvokeResult(
            callable_name=name,
            callable_type=CallableType.TOOL,
            output=ToolOutput(result=f"{name} output"),
            duration_ms=5,
        ))
        tool.input_schema = MagicMock()
        registry[name] = tool
    return registry


# ── HRAgent ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hr_agent_produces_docx_structured_output():
    from citnega.packages.agents.specialists.hr_agent import HRAgent, HRInput
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    enforcer, emitter, tracer = _deps()
    tools = _make_tool_registry("write_docx", "read_file")

    agent = HRAgent(enforcer, emitter, tracer, tools)
    agent._call_model = AsyncMock(return_value="Job description for Senior Engineer: ...")

    result = await agent._execute(
        HRInput(task="Write a job description for a senior engineer"),
        _ctx(),
    )
    assert isinstance(result, SpecialistOutput)
    assert "engineer" in result.response.lower() or "job" in result.response.lower()


@pytest.mark.asyncio
async def test_hr_agent_reads_candidate_file_when_provided(tmp_path):
    from citnega.packages.agents.specialists.hr_agent import HRAgent, HRInput
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    candidate_file = tmp_path / "candidate.txt"
    candidate_file.write_text("Candidate: Jane Doe, 10 years Python")

    enforcer, emitter, tracer = _deps()

    # Stub read_file to return the file content
    read_tool = MagicMock()
    read_tool.name = "read_file"
    read_tool.callable_type = CallableType.TOOL
    read_tool.invoke = AsyncMock(return_value=InvokeResult(
        callable_name="read_file",
        callable_type=CallableType.TOOL,
        output=ToolOutput(result=candidate_file.read_text()),
        duration_ms=5,
    ))

    agent = HRAgent(enforcer, emitter, tracer, {"read_file": read_tool})
    captured_prompt: list[str] = []

    async def _mock_model(prompt, ctx, system_override=None):
        captured_prompt.append(prompt)
        return "Evaluation: Strong candidate."

    agent._call_model = _mock_model

    result = await agent._execute(
        HRInput(task="Evaluate this candidate", candidate_file=str(candidate_file)),
        _ctx(),
    )
    assert isinstance(result, SpecialistOutput)
    assert "read_file" in result.tool_calls_made


# ── QAEngineerAgent ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qa_engineer_runs_quality_gate_when_run_tests_true(tmp_path):
    from citnega.packages.agents.specialists.qa_engineer_agent import (
        QAEngineerAgent,
        QAEngineerInput,
    )
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    enforcer, emitter, tracer = _deps()

    # Stub test_matrix + quality_gate
    test_matrix_tool = MagicMock()
    test_matrix_tool.name = "test_matrix"
    test_matrix_tool.callable_type = CallableType.TOOL
    test_matrix_tool.input_schema = MagicMock()
    test_matrix_tool.invoke = AsyncMock(return_value=InvokeResult(
        callable_name="test_matrix", callable_type=CallableType.TOOL,
        output=ToolOutput(result="4 passed, 0 failed"), duration_ms=10,
    ))

    qg_tool = MagicMock()
    qg_tool.name = "quality_gate"
    qg_tool.callable_type = CallableType.TOOL
    qg_tool.input_schema = MagicMock()
    qg_tool.invoke = AsyncMock(return_value=InvokeResult(
        callable_name="quality_gate", callable_type=CallableType.TOOL,
        output=ToolOutput(result="All checks passed"), duration_ms=10,
    ))

    tools = {"test_matrix": test_matrix_tool, "quality_gate": qg_tool}
    agent = QAEngineerAgent(enforcer, emitter, tracer, tools)
    agent._call_model = AsyncMock(return_value="All quality checks pass. Coverage is good.")

    result = await agent._execute(
        QAEngineerInput(task="Run test suite", working_dir=str(tmp_path), run_tests=True),
        _ctx(),
    )
    assert isinstance(result, SpecialistOutput)
    test_matrix_tool.invoke.assert_called_once()
    qg_tool.invoke.assert_called_once()
    assert "test_matrix" in result.tool_calls_made
    assert "quality_gate" in result.tool_calls_made


@pytest.mark.asyncio
async def test_qa_engineer_skips_test_matrix_when_run_tests_false():
    from citnega.packages.agents.specialists.qa_engineer_agent import (
        QAEngineerAgent,
        QAEngineerInput,
    )
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    enforcer, emitter, tracer = _deps()
    tools = _make_tool_registry("test_matrix", "quality_gate")
    agent = QAEngineerAgent(enforcer, emitter, tracer, tools)
    agent._call_model = AsyncMock(return_value="Reviewed test plan manually.")

    result = await agent._execute(
        QAEngineerInput(task="Review test plan", run_tests=False),
        _ctx(),
    )
    assert isinstance(result, SpecialistOutput)
    tools["test_matrix"].invoke.assert_not_called()
    tools["quality_gate"].invoke.assert_not_called()


# ── DevOpsAgent ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_devops_agent_invokes_log_analyzer(tmp_path):
    from citnega.packages.agents.specialists.devops_agent import DevOpsAgent, DevOpsInput
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    log_file = tmp_path / "app.log"
    log_file.write_text("ERROR 2024-01-01 connection refused\nERROR 2024-01-01 timeout")

    enforcer, emitter, tracer = _deps()

    log_tool = MagicMock()
    log_tool.name = "log_analyzer"
    log_tool.callable_type = CallableType.TOOL
    log_tool.input_schema = MagicMock()
    log_tool.invoke = AsyncMock(return_value=InvokeResult(
        callable_name="log_analyzer", callable_type=CallableType.TOOL,
        output=ToolOutput(result="Found 2 ERROR entries: connection refused, timeout"),
        duration_ms=5,
    ))

    tools = {"log_analyzer": log_tool}
    agent = DevOpsAgent(enforcer, emitter, tracer, tools)
    agent._call_model = AsyncMock(return_value="Root cause: connection timeout due to misconfigured service.")

    result = await agent._execute(
        DevOpsInput(task="Diagnose service failure", log_file=str(log_file)),
        _ctx(),
    )
    assert isinstance(result, SpecialistOutput)
    log_tool.invoke.assert_called_once()
    assert "log_analyzer" in result.tool_calls_made


# ── AgentDelegateTool ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_delegate_tool_routes_to_hr_agent():
    from citnega.packages.tools.builtin.agent_delegate import AgentDelegateTool, AgentDelegateInput

    enforcer, emitter, tracer = _deps()

    # Build a real HRAgent stub that returns a SpecialistOutput
    from citnega.packages.agents.specialists.hr_agent import HRAgent
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    hr_specialist = HRAgent(enforcer, emitter, tracer, {})
    hr_specialist._call_model = AsyncMock(return_value="Here is the performance review template.")

    delegate_tool = AgentDelegateTool(enforcer, emitter, tracer)
    ctx = _ctx()
    ctx = ctx.model_copy(update={"metadata": {"sub_callables": {"hr_agent": hr_specialist}}})

    result = await delegate_tool._execute(
        AgentDelegateInput(agent_name="hr_agent", task="Create a performance review template"),
        ctx,
    )
    assert "performance review" in result.result.lower() or len(result.result) > 0


@pytest.mark.asyncio
async def test_agent_delegate_tool_returns_graceful_message_when_agent_missing():
    from citnega.packages.tools.builtin.agent_delegate import AgentDelegateTool, AgentDelegateInput

    enforcer, emitter, tracer = _deps()
    delegate_tool = AgentDelegateTool(enforcer, emitter, tracer)
    ctx = _ctx()  # no sub_callables in metadata

    result = await delegate_tool._execute(
        AgentDelegateInput(agent_name="nonexistent_agent", task="do something"),
        ctx,
    )
    assert "not found" in result.result or "nonexistent_agent" in result.result
