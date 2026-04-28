"""Unit tests for Batch 4 new specialist agents."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer


def _deps():
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return enforcer, emitter, tracer


def _make_specialist(cls):
    enforcer, emitter, tracer = _deps()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


def _context():
    return CallContext(
        session_id="test",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="test", name="test", framework="stub", default_model_id="x"
        ),
    )


# ── Name and type contracts ───────────────────────────────────────────────────

def test_hr_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.hr_agent import HRAgent
    a = _make_specialist(HRAgent)
    assert a.name == "hr_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_product_manager_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.product_manager_agent import ProductManagerAgent
    a = _make_specialist(ProductManagerAgent)
    assert a.name == "product_manager_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_marketing_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.marketing_agent import MarketingAgent
    a = _make_specialist(MarketingAgent)
    assert a.name == "marketing_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_sales_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.sales_agent import SalesAgent
    a = _make_specialist(SalesAgent)
    assert a.name == "sales_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_ux_design_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.ux_design_agent import UXDesignAgent
    a = _make_specialist(UXDesignAgent)
    assert a.name == "ux_design_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_customer_support_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.customer_support_agent import CustomerSupportAgent
    a = _make_specialist(CustomerSupportAgent)
    assert a.name == "customer_support_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_devops_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.devops_agent import DevOpsAgent
    a = _make_specialist(DevOpsAgent)
    assert a.name == "devops_agent"
    assert a.callable_type == CallableType.SPECIALIST


def test_qa_engineer_agent_name_and_callable_type():
    from citnega.packages.agents.specialists.qa_engineer_agent import QAEngineerAgent
    a = _make_specialist(QAEngineerAgent)
    assert a.name == "qa_engineer_agent"
    assert a.callable_type == CallableType.SPECIALIST


# ── TOOL_WHITELIST checks ─────────────────────────────────────────────────────

def test_hr_agent_tool_whitelist_contains_write_docx():
    from citnega.packages.agents.specialists.hr_agent import HRAgent
    assert "write_docx" in HRAgent.TOOL_WHITELIST


def test_devops_agent_tool_whitelist_contains_run_shell():
    from citnega.packages.agents.specialists.devops_agent import DevOpsAgent
    assert "run_shell" in DevOpsAgent.TOOL_WHITELIST


def test_qa_engineer_agent_tool_whitelist_contains_quality_gate():
    from citnega.packages.agents.specialists.qa_engineer_agent import QAEngineerAgent
    assert "quality_gate" in QAEngineerAgent.TOOL_WHITELIST


def test_customer_support_agent_tool_whitelist_contains_read_kb():
    from citnega.packages.agents.specialists.customer_support_agent import CustomerSupportAgent
    assert "read_kb" in CustomerSupportAgent.TOOL_WHITELIST


# ── Invoke with mocked _call_model ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hr_agent_invoke_returns_specialist_output():
    from citnega.packages.agents.specialists.hr_agent import HRAgent, HRInput
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    a = _make_specialist(HRAgent)
    a._call_model = AsyncMock(return_value="Here is the job description.")
    result = await a._execute(HRInput(task="write job description for senior engineer"), _context())
    assert isinstance(result, SpecialistOutput)
    assert "job description" in result.response


@pytest.mark.asyncio
async def test_qa_engineer_no_run_tests_skips_tool_calls():
    from citnega.packages.agents.specialists.qa_engineer_agent import QAEngineerAgent, QAEngineerInput
    from citnega.packages.agents.specialists._specialist_base import SpecialistOutput

    a = _make_specialist(QAEngineerAgent)
    a._call_model = AsyncMock(return_value="Coverage looks good.")
    result = await a._execute(
        QAEngineerInput(task="review test coverage", run_tests=False), _context()
    )
    assert isinstance(result, SpecialistOutput)
    # No tool calls expected when run_tests=False and no working_dir
    assert "test_matrix" not in result.tool_calls_made
    assert "quality_gate" not in result.tool_calls_made


# ── ALL_SPECIALISTS registration ──────────────────────────────────────────────

def test_all_new_specialists_in_ALL_SPECIALISTS_list():
    from citnega.packages.agents.specialists import ALL_SPECIALISTS
    names = {cls.name for cls in ALL_SPECIALISTS}
    expected = {
        "hr_agent", "product_manager_agent", "marketing_agent", "sales_agent",
        "ux_design_agent", "customer_support_agent", "devops_agent", "qa_engineer_agent",
    }
    missing = expected - names
    assert not missing, f"Missing from ALL_SPECIALISTS: {missing}"
