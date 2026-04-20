"""Performance: PlanScheduler.build_batches() must handle a 100-step plan in < 5ms."""

from __future__ import annotations

import time
import uuid

from citnega.packages.capabilities.registry import CapabilityRegistry
from citnega.packages.execution.scheduler import PlanScheduler
from citnega.packages.planning.models import CompiledPlan, PlanStep, PlanStepType


def _make_plan(n_steps: int, max_parallelism: int = 4) -> CompiledPlan:
    steps = [
        PlanStep(
            step_id=f"step_{i}",
            step_type=PlanStepType.TOOL,
            capability_id="stub_tool",
            task=f"task {i}",
            can_run_in_parallel=True,
        )
        for i in range(n_steps)
    ]
    return CompiledPlan(
        plan_id=str(uuid.uuid4()),
        objective="perf test",
        steps=steps,
        generated_from="test",
        max_parallelism=max_parallelism,
    )


def _make_chained_plan(n_steps: int) -> CompiledPlan:
    """Sequential chain: each step depends on the previous."""
    steps = []
    for i in range(n_steps):
        steps.append(
            PlanStep(
                step_id=f"step_{i}",
                step_type=PlanStepType.TOOL,
                capability_id="stub_tool",
                task=f"task {i}",
                depends_on=[f"step_{i - 1}"] if i > 0 else [],
                can_run_in_parallel=False,
            )
        )
    return CompiledPlan(
        plan_id=str(uuid.uuid4()),
        objective="perf test chained",
        steps=steps,
        generated_from="test",
        max_parallelism=1,
    )


class TestSchedulerOverhead:
    """PlanScheduler.build_batches() latency budget: 100-step plan < 5ms."""

    def test_parallel_100_steps_under_5ms(self) -> None:
        plan = _make_plan(100, max_parallelism=8)
        registry = CapabilityRegistry()
        scheduler = PlanScheduler()

        start = time.monotonic()
        batches = scheduler.build_batches(plan, registry)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(batches) > 0, "Expected at least one batch"
        total_scheduled = sum(len(b.step_ids) for b in batches)
        assert total_scheduled == 100
        assert elapsed_ms < 5.0, f"build_batches took {elapsed_ms:.2f}ms for 100 steps (limit: 5ms)"

    def test_chained_100_steps_under_5ms(self) -> None:
        plan = _make_chained_plan(100)
        registry = CapabilityRegistry()
        scheduler = PlanScheduler()

        start = time.monotonic()
        batches = scheduler.build_batches(plan, registry)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(batches) == 100, "Sequential chain should produce one batch per step"
        assert elapsed_ms < 5.0, f"build_batches took {elapsed_ms:.2f}ms for chained 100 steps (limit: 5ms)"

    def test_large_plan_200_steps_under_10ms(self) -> None:
        plan = _make_plan(200, max_parallelism=16)
        registry = CapabilityRegistry()
        scheduler = PlanScheduler()

        start = time.monotonic()
        batches = scheduler.build_batches(plan, registry)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert sum(len(b.step_ids) for b in batches) == 200
        assert elapsed_ms < 10.0, f"build_batches took {elapsed_ms:.2f}ms for 200 steps (limit: 10ms)"
