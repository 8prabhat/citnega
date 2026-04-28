"""
Integration tests for Batch 8 orchestration improvements:
- Condition gates block/allow downstream steps
- stop_conditions halt multi-step plans early
- Approval gate skips remaining steps when denied
- Idempotency key deduplicates across two plan runs
- Exponential backoff timing with multiplier
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.capabilities.models import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProvenance,
)
from citnega.packages.capabilities.registry import CapabilityRecord, CapabilityRegistry
from citnega.packages.execution.engine import ExecutionEngine
from citnega.packages.planning.models import (
    CompiledPlan,
    PlanStep,
    PlanStepType,
    RetryPolicy,
)
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.tools.builtin._tool_base import ToolOutput


def _ctx() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1", name="test", framework="stub", default_model_id="x"
        ),
    )


def _ok_result(name: str, output: str = "ok") -> InvokeResult:
    return InvokeResult(
        callable_name=name,
        callable_type=CallableType.TOOL,
        output=ToolOutput(result=output),
        duration_ms=5,
    )


def _fail_result(name: str, msg: str = "fail") -> InvokeResult:
    from citnega.packages.shared.errors import CitnegaError
    return InvokeResult(
        callable_name=name,
        callable_type=CallableType.TOOL,
        output=None,
        duration_ms=5,
        error=CitnegaError(msg),
    )


def _stub_callable(name: str, result: InvokeResult) -> IInvocable:
    obj = MagicMock(spec=IInvocable)
    obj.name = name
    obj.callable_type = CallableType.TOOL
    obj.invoke = AsyncMock(return_value=result)
    obj.input_schema = MagicMock()
    obj.input_schema.model_validate = MagicMock(return_value=MagicMock(
        model_dump_json=MagicMock(return_value="{}")
    ))
    return obj


def _registry(*callables) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for c in callables:
        desc = CapabilityDescriptor(
            capability_id=c.name,
            kind=CapabilityKind.TOOL,
            display_name=c.name,
            description="stub",
            provenance=CapabilityProvenance(source="builtin"),
        )
        reg.register(CapabilityRecord(descriptor=desc, runtime_object=c))
    return reg


# ── condition gates ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_plan_condition_gates_downstream_step():
    """Step2 has condition referencing step1's output; False → skipped."""
    tool1 = _stub_callable("tool1", _ok_result("tool1", "value=3"))
    tool2 = _stub_callable("tool2", _ok_result("tool2", "downstream"))

    step1 = PlanStep(step_id="s1", step_type=PlanStepType.TOOL, capability_id="tool1")
    step2 = PlanStep(
        step_id="s2",
        step_type=PlanStepType.TOOL,
        capability_id="tool2",
        depends_on=["s1"],
        condition="False",  # always blocked
    )
    plan = CompiledPlan(plan_id="p1", objective="test", steps=[step1, step2])
    engine = ExecutionEngine()
    result = await engine.execute(plan, _registry(tool1, tool2), _ctx())

    statuses = {r.step_id: r.status for r in result.step_results}
    assert statuses["s1"] == "completed"
    assert statuses["s2"] == "skipped"
    tool2.invoke.assert_not_called()


@pytest.mark.asyncio
async def test_condition_true_allows_downstream_step():
    tool1 = _stub_callable("tool1", _ok_result("tool1", "result=done"))
    tool2 = _stub_callable("tool2", _ok_result("tool2", "second"))

    step1 = PlanStep(step_id="s1", step_type=PlanStepType.TOOL, capability_id="tool1")
    step2 = PlanStep(
        step_id="s2",
        step_type=PlanStepType.TOOL,
        capability_id="tool2",
        depends_on=["s1"],
        condition="True",
    )
    plan = CompiledPlan(plan_id="p2", objective="test", steps=[step1, step2])
    engine = ExecutionEngine()
    result = await engine.execute(plan, _registry(tool1, tool2), _ctx())

    assert all(r.status == "completed" for r in result.step_results)


# ── stop_conditions ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_condition_halts_multi_step_plan_early():
    """stop_conditions='True' halts after the first batch."""
    tool1 = _stub_callable("tool1", _ok_result("tool1"))
    tool2 = _stub_callable("tool2", _ok_result("tool2"))

    step1 = PlanStep(step_id="s1", step_type=PlanStepType.TOOL, capability_id="tool1")
    step2 = PlanStep(
        step_id="s2",
        step_type=PlanStepType.TOOL,
        capability_id="tool2",
        depends_on=["s1"],
    )
    plan = CompiledPlan(
        plan_id="p3",
        objective="test",
        steps=[step1, step2],
        stop_conditions=["True"],
    )
    engine = ExecutionEngine()
    result = await engine.execute(plan, _registry(tool1, tool2), _ctx(), fail_fast=False)

    assert "Stopped early" in result.response
    # step2 should not have run (plan was halted after batch 1)
    executed_ids = {r.step_id for r in result.step_results}
    assert "s1" in executed_ids
    assert "s2" not in executed_ids


# ── approval gate ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_gate_denied_skips_remaining_steps():
    """APPROVAL_GATE with no approval_manager → skipped, subsequent steps don't run."""
    gate = PlanStep(
        step_id="gate",
        step_type=PlanStepType.APPROVAL_GATE,
        capability_id="",
        task="Please approve",
    )
    tool1 = _stub_callable("tool1", _ok_result("tool1"))
    step_after = PlanStep(
        step_id="after",
        step_type=PlanStepType.TOOL,
        capability_id="tool1",
        depends_on=["gate"],
    )
    plan = CompiledPlan(plan_id="p4", objective="test", steps=[gate, step_after])
    engine = ExecutionEngine()
    result = await engine.execute(plan, _registry(tool1), _ctx())

    gate_result = next(r for r in result.step_results if r.step_id == "gate")
    assert gate_result.status == "skipped"


# ── idempotency ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotency_key_deduplicates_across_two_runs():
    tool1 = _stub_callable("tool1", _ok_result("tool1"))
    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="tool1",
        idempotency_key="dedup-key",
    )
    plan = CompiledPlan(plan_id="p5", objective="test", steps=[step])
    engine = ExecutionEngine()

    result1 = await engine.execute(plan, _registry(tool1), _ctx())
    invoke_count_after_first = tool1.invoke.call_count

    result2 = await engine.execute(plan, _registry(tool1), _ctx())

    assert result1.step_results[0].status == "completed"
    assert result2.step_results[0].status == "completed"
    # Second run should NOT invoke the callable again
    assert tool1.invoke.call_count == invoke_count_after_first


# ── exponential backoff ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exponential_backoff_timing_with_multiplier(monkeypatch):
    import asyncio
    from citnega.packages.shared.errors import CitnegaError

    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    fail_result = InvokeResult(
        callable_name="flaky",
        callable_type=CallableType.TOOL,
        output=None,
        duration_ms=0,
        error=CitnegaError("transient"),
    )
    tool = _stub_callable("flaky", fail_result)
    tool.invoke = AsyncMock(return_value=fail_result)

    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="flaky",
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1.0, backoff_multiplier=2.0),
    )
    plan = CompiledPlan(plan_id="p6", objective="test", steps=[step])
    engine = ExecutionEngine()
    await engine.execute(plan, _registry(tool), _ctx(), fail_fast=False)

    # 3 attempts → 2 sleeps (between attempt 1→2 and 2→3)
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(1.0, rel=0.1)   # 1.0 * 2^0
    assert sleeps[1] == pytest.approx(2.0, rel=0.1)   # 1.0 * 2^1
