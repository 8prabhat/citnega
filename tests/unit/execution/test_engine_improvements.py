"""
Unit tests for Batch 5 engine improvements:
- condition evaluation (skip when false, run when true)
- idempotency key caching
- step output propagation (placeholder substitution)
- exponential backoff timing
- APPROVAL_GATE skipped when approval_manager not available
- stop_conditions halt execution early
- safe_eval: allows comparisons, rejects function calls, rejects imports
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.execution.engine import ExecutionEngine
from citnega.packages.execution.models import ExecutionResult
from citnega.packages.execution.scheduler import PlanScheduler
from citnega.packages.planning.models import (
    CompiledPlan,
    PlanStep,
    PlanStepType,
    RetryPolicy,
)
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1", name="test", framework="stub", default_model_id="x"
        ),
    )


def _plan_with_steps(steps: list[PlanStep]) -> CompiledPlan:
    return CompiledPlan(
        plan_id="plan1",
        objective="test",
        steps=steps,
    )


def _mock_registry(step_id: str, output_excerpt: str = "ok") -> MagicMock:
    """Registry that returns a successful invocable for the given capability_id."""
    from citnega.packages.protocol.callables.results import InvokeResult
    from citnega.packages.protocol.callables.types import CallableType
    from citnega.packages.tools.builtin._tool_base import ToolOutput

    mock_callable = MagicMock()
    mock_callable.name = step_id
    mock_callable.callable_type = CallableType.TOOL

    class _FakeInput(MagicMock):
        model_dump_json = MagicMock(return_value="{}")

    mock_callable.input_schema = MagicMock(return_value=_FakeInput())
    mock_callable.input_schema.model_validate = MagicMock(return_value=_FakeInput())

    output = ToolOutput(result=output_excerpt)
    invoke_result = InvokeResult(
        callable_name=step_id,
        callable_type=CallableType.TOOL,
        output=output,
        duration_ms=10,
    )

    mock_callable.invoke = AsyncMock(return_value=invoke_result)
    from citnega.packages.protocol.callables.interfaces import IInvocable
    mock_callable.__class__ = type("MockInvocable", (IInvocable,), {})

    registry = MagicMock()
    registry.get_runtime = MagicMock(return_value=mock_callable)
    return registry


# ── safe_eval ─────────────────────────────────────────────────────────────────

def test_safe_eval_allows_comparisons():
    from citnega.packages.shared.safe_eval import safe_eval
    assert safe_eval("x > 5", {"x": 10}) is True
    assert safe_eval("x > 5", {"x": 3}) is False


def test_safe_eval_allows_string_in_check():
    from citnega.packages.shared.safe_eval import safe_eval
    assert safe_eval("'error' in result", {"result": "some error occurred"}) is True
    assert safe_eval("'error' in result", {"result": "all good"}) is False


def test_safe_eval_rejects_function_calls():
    from citnega.packages.shared.safe_eval import safe_eval
    with pytest.raises(ValueError, match="[Dd]isallowed"):
        safe_eval("len(x) > 0", {"x": [1, 2]})


def test_safe_eval_rejects_import_nodes():
    from citnega.packages.shared.safe_eval import safe_eval
    with pytest.raises((ValueError, SyntaxError)):
        safe_eval("__import__('os').system('ls')", {})


def test_safe_eval_returns_false_on_eval_error():
    from citnega.packages.shared.safe_eval import safe_eval
    result = safe_eval("undefined_var > 0", {})
    assert result is False


# ── Condition evaluation ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_condition_skips_step_when_false():
    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="my_tool",
        condition="False",
    )
    plan = _plan_with_steps([step])
    engine = ExecutionEngine()
    registry = _mock_registry("my_tool")
    result = await engine.execute(plan, registry, _context())
    assert result.step_results[0].status == "skipped"


@pytest.mark.asyncio
async def test_condition_runs_step_when_true():
    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="my_tool",
        condition="True",
    )
    plan = _plan_with_steps([step])
    engine = ExecutionEngine()
    registry = _mock_registry("my_tool")
    result = await engine.execute(plan, registry, _context())
    assert result.step_results[0].status == "completed"


# ── Idempotency ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_idempotency_key_returns_cached_result():
    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="my_tool",
        idempotency_key="key-abc",
    )
    plan = _plan_with_steps([step])
    engine = ExecutionEngine()
    registry = _mock_registry("my_tool")

    # First run
    result1 = await engine.execute(plan, registry, _context())
    assert result1.step_results[0].status == "completed"
    call_count_after_first = registry.get_runtime.return_value.invoke.call_count

    # Second run — should use cache, not invoke again
    result2 = await engine.execute(plan, registry, _context())
    assert result2.step_results[0].status == "completed"
    assert registry.get_runtime.return_value.invoke.call_count == call_count_after_first


# ── Step output propagation ────────────────────────────────────────────────────

def test_step_output_propagation_substitutes_placeholder():
    from citnega.packages.execution.engine import ExecutionEngine
    from citnega.packages.execution.models import ExecutionStepResult
    from pydantic import BaseModel

    class _Input(BaseModel):
        task: str = ""

    step = PlanStep(
        step_id="s2",
        step_type=PlanStepType.TOOL,
        capability_id="tool",
        args={"task": "Process: {s1.result}"},
    )
    completed = {
        "s1": ExecutionStepResult(
            step_id="s1", capability_id="c1", status="completed",
            attempts=1, dependency_ids=[], output_excerpt="hello world",
        )
    }
    engine = ExecutionEngine()
    built = engine._build_input(_Input, step, completed)
    assert "hello world" in built.task


# ── Exponential backoff ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_exponential_backoff_delay_doubles(monkeypatch):
    import asyncio
    sleeps: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    from citnega.packages.protocol.callables.results import InvokeResult
    from citnega.packages.protocol.callables.types import CallableType
    from citnega.packages.shared.errors import CitnegaError

    fail_result = InvokeResult(
        callable_name="flaky_tool",
        callable_type=CallableType.TOOL,
        duration_ms=0,
        error=CitnegaError("transient error"),
    )

    mock_callable = MagicMock()
    mock_callable.callable_type = CallableType.TOOL
    mock_callable.name = "flaky_tool"
    mock_callable.input_schema.model_validate = MagicMock(return_value=MagicMock(model_dump_json=MagicMock(return_value="{}")))
    mock_callable.invoke = AsyncMock(return_value=fail_result)
    from citnega.packages.protocol.callables.interfaces import IInvocable
    mock_callable.__class__ = type("MockInvocable", (IInvocable,), {})

    registry = MagicMock()
    registry.get_runtime = MagicMock(return_value=mock_callable)

    step = PlanStep(
        step_id="s1",
        step_type=PlanStepType.TOOL,
        capability_id="flaky_tool",
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1.0, backoff_multiplier=2.0),
    )
    plan = _plan_with_steps([step])
    engine = ExecutionEngine()
    await engine.execute(plan, registry, _context(), fail_fast=False)

    assert len(sleeps) == 2  # attempts 1→2 and 2→3
    assert sleeps[1] == pytest.approx(2.0, rel=0.1)  # 1.0 * 2^1 = 2.0


# ── APPROVAL_GATE ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approval_gate_skips_on_no_approval_manager():
    step = PlanStep(
        step_id="gate1",
        step_type=PlanStepType.APPROVAL_GATE,
        capability_id="",
        task="Please approve deployment",
    )
    plan = _plan_with_steps([step])
    engine = ExecutionEngine()
    registry = MagicMock()
    result = await engine.execute(plan, registry, _context())
    assert result.step_results[0].status == "skipped"


# ── stop_conditions ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stop_conditions_halt_execution_early():
    step1 = PlanStep(step_id="s1", step_type=PlanStepType.TOOL, capability_id="t1")
    step2 = PlanStep(step_id="s2", step_type=PlanStepType.TOOL, capability_id="t2", depends_on=["s1"])

    plan = CompiledPlan(
        plan_id="p1",
        objective="test stop",
        steps=[step1, step2],
        stop_conditions=["True"],  # always stop after first batch
    )
    engine = ExecutionEngine()
    registry = _mock_registry("t1")
    result = await engine.execute(plan, registry, _context())
    assert "Stopped early" in result.response
