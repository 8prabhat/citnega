from __future__ import annotations

from citnega.packages.capabilities import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProvenance,
    CapabilityRecord,
    CapabilityRegistry,
)
from citnega.packages.planning import CompiledPlan, PlanStep, PlanStepType, PlanValidator


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityRecord(
            descriptor=CapabilityDescriptor(
                capability_id="qa_agent",
                kind=CapabilityKind.AGENT,
                display_name="qa_agent",
                description="QA",
                provenance=CapabilityProvenance(source="test"),
            )
        )
    )
    return registry


def test_plan_validator_reports_missing_capability_and_dependency_cycle():
    plan = CompiledPlan(
        plan_id="p1",
        objective="review",
        max_parallelism=1,
        steps=[
            PlanStep(
                step_id="one",
                step_type=PlanStepType.AGENT,
                capability_id="qa_agent",
                depends_on=["two"],
            ),
            PlanStep(
                step_id="two",
                step_type=PlanStepType.AGENT,
                capability_id="missing_agent",
                depends_on=["one"],
            ),
        ],
    )

    report = PlanValidator().validate(plan, _registry())

    assert not report.valid
    assert any("unknown capability 'missing_agent'" in error for error in report.errors)
    assert any("dependency cycle" in error for error in report.errors)
