from __future__ import annotations

from citnega.packages.capabilities.registry import CapabilityRegistry
from citnega.packages.execution.models import ExecutionBatch
from citnega.packages.planning.models import CompiledPlan, PlanStep


class PlanScheduler:
    def build_batches(self, plan: CompiledPlan, registry: CapabilityRegistry) -> list[ExecutionBatch]:
        pending = {step.step_id: step for step in plan.steps}
        satisfied: set[str] = set()
        batches: list[ExecutionBatch] = []
        batch_index = 0

        while pending:
            ready = [
                step
                for step in plan.steps
                if step.step_id in pending and all(dep in satisfied for dep in step.depends_on)
            ]
            if not ready:
                unresolved = sorted(pending)
                batches.append(ExecutionBatch(batch_id=f"batch-{batch_index}", step_ids=unresolved))
                break

            stage_capacity = max(1, plan.max_parallelism)
            while ready:
                current: list[PlanStep] = []
                for step in list(ready):
                    if len(current) >= stage_capacity:
                        break
                    if self._conflicts(step, current, registry):
                        continue
                    current.append(step)
                    ready.remove(step)
                if not current:
                    current = [ready.pop(0)]
                batch = ExecutionBatch(batch_id=f"batch-{batch_index}", step_ids=[step.step_id for step in current])
                batches.append(batch)
                batch_index += 1
                for step in current:
                    pending.pop(step.step_id, None)
                    satisfied.add(step.step_id)

        return batches

    def _conflicts(
        self,
        candidate: PlanStep,
        selected: list[PlanStep],
        registry: CapabilityRegistry,
    ) -> bool:
        descriptor = registry.get_descriptor(candidate.capability_id)
        if descriptor is None:
            return False
        traits = descriptor.execution_traits
        if not candidate.can_run_in_parallel or not traits.parallel_safe:
            return bool(selected)
        if traits.requires_exclusive_workspace:
            return bool(selected)
        candidate_scope = self._resource_scope(candidate, descriptor.execution_traits.resource_scope)
        for existing in selected:
            existing_descriptor = registry.get_descriptor(existing.capability_id)
            if existing_descriptor is None:
                continue
            existing_scope = self._resource_scope(existing, existing_descriptor.execution_traits.resource_scope)
            if existing_scope and candidate_scope and existing_scope == candidate_scope:
                return True
            if existing_descriptor.execution_traits.requires_exclusive_workspace:
                return True
        return False

    @staticmethod
    def _resource_scope(step: PlanStep, default_scope: str) -> str:
        for key in ("file_path", "root_path", "working_dir", "path"):
            value = step.args.get(key)
            if isinstance(value, str) and value.strip():
                return f"{key}:{value}"
        return default_scope
