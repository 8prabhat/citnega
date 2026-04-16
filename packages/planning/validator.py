from __future__ import annotations

from citnega.packages.capabilities.models import CapabilityKind
from citnega.packages.capabilities.registry import CapabilityRegistry
from citnega.packages.planning.models import CompiledPlan, PlanStepType, ValidationReport


class PlanValidator:
    def validate(self, plan: CompiledPlan, registry: CapabilityRegistry) -> ValidationReport:
        errors: list[str] = []
        step_ids = [step.step_id for step in plan.steps]
        if len(step_ids) != len(set(step_ids)):
            errors.append("Plan contains duplicate step ids.")

        known_step_ids = set(step_ids)
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in known_step_ids:
                    errors.append(f"Step {step.step_id!r} depends on unknown step {dep!r}.")
            if step.step_type not in {PlanStepType.SYNTHESIS, PlanStepType.APPROVAL_GATE}:
                descriptor = registry.get_descriptor(step.capability_id)
                if descriptor is None:
                    errors.append(
                        f"Step {step.step_id!r} references unknown capability {step.capability_id!r}."
                    )
                elif step.step_type == PlanStepType.WORKFLOW_TEMPLATE_REF and descriptor.kind != CapabilityKind.WORKFLOW_TEMPLATE:
                    errors.append(
                        f"Step {step.step_id!r} must reference a workflow template capability."
                    )

        if self._has_cycle(plan):
            errors.append("Plan contains a dependency cycle.")

        if plan.max_parallelism < 1:
            errors.append("Plan max_parallelism must be >= 1.")

        return ValidationReport(valid=not errors, errors=errors)

    def _has_cycle(self, plan: CompiledPlan) -> bool:
        graph = {step.step_id: list(step.depends_on) for step in plan.steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visited:
                return False
            if node in visiting:
                return True
            visiting.add(node)
            for dependency in graph.get(node, []):
                if visit(dependency):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph)
