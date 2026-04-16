from __future__ import annotations

from citnega.packages.capabilities import (
    CapabilityDescriptor,
    CapabilityExecutionTraits,
    CapabilityKind,
    CapabilityProvenance,
    CapabilityRecord,
    CapabilityRegistry,
)
from citnega.packages.execution import PlanScheduler
from citnega.packages.planning import CompiledPlan, PlanStep, PlanStepType


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityRecord(
            descriptor=CapabilityDescriptor(
                capability_id="search_files",
                kind=CapabilityKind.TOOL,
                display_name="search_files",
                description="Search",
                execution_traits=CapabilityExecutionTraits(
                    parallel_safe=True,
                    resource_scope="workspace",
                ),
                provenance=CapabilityProvenance(source="test"),
            )
        )
    )
    registry.register(
        CapabilityRecord(
            descriptor=CapabilityDescriptor(
                capability_id="read_file",
                kind=CapabilityKind.TOOL,
                display_name="read_file",
                description="Read",
                execution_traits=CapabilityExecutionTraits(
                    parallel_safe=True,
                    resource_scope="workspace",
                ),
                provenance=CapabilityProvenance(source="test"),
            )
        )
    )
    return registry


def test_scheduler_batches_parallel_safe_steps_and_serializes_conflicts():
    plan = CompiledPlan(
        plan_id="p1",
        objective="inspect",
        max_parallelism=2,
        steps=[
            PlanStep(
                step_id="one",
                step_type=PlanStepType.TOOL,
                capability_id="search_files",
                args={"path": "/tmp/a"},
                can_run_in_parallel=True,
            ),
            PlanStep(
                step_id="two",
                step_type=PlanStepType.TOOL,
                capability_id="read_file",
                args={"path": "/tmp/b"},
                can_run_in_parallel=True,
            ),
            PlanStep(
                step_id="three",
                step_type=PlanStepType.TOOL,
                capability_id="read_file",
                args={"path": "/tmp/b"},
                can_run_in_parallel=True,
            ),
        ],
    )

    batches = PlanScheduler().build_batches(plan, _registry())

    assert batches[0].step_ids == ["one", "two"]
    assert batches[1].step_ids == ["three"]
