from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from citnega.packages.capabilities.registry import CapabilityRegistry
from citnega.packages.execution.models import ExecutionBatch, ExecutionResult, ExecutionStepResult
from citnega.packages.execution.scheduler import PlanScheduler
from citnega.packages.planning.models import CompiledPlan, PlanStep
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.shared.errors import CitnegaError, InvalidConfigError

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.events import IEventEmitter

_TEXT_FIELD_CANDIDATES = ("task", "query", "goal", "text", "user_input", "prompt", "objective")


class ExecutionEngine:
    def __init__(
        self,
        scheduler: PlanScheduler | None = None,
        *,
        event_emitter: IEventEmitter | None = None,
    ) -> None:
        self._scheduler = scheduler or PlanScheduler()
        self._event_emitter = event_emitter

    async def execute(
        self,
        plan: CompiledPlan,
        registry: CapabilityRegistry,
        context: CallContext,
        *,
        fail_fast: bool = True,
        rollback_on_failure: bool = False,
    ) -> ExecutionResult:
        batches = self._scheduler.build_batches(plan, registry)
        step_lookup = {step.step_id: step for step in plan.steps}
        result = ExecutionResult(batches=batches)
        completed: dict[str, ExecutionStepResult] = {}
        successful_steps: list[PlanStep] = []
        result_map: dict[str, ExecutionStepResult] = {}

        for batch in batches:
            pending_steps = [step_lookup[step_id] for step_id in batch.step_ids if step_id in step_lookup]
            if not pending_steps:
                continue
            self._emit_batch_started(plan, batch, context)
            batch_results = await self._run_batch(pending_steps, registry, context)
            self._emit_batch_completed(plan, batch, batch_results, context)
            result.step_results.extend(batch_results)
            for step_result in batch_results:
                completed[step_result.step_id] = step_result
                result_map[step_result.step_id] = step_result
                if step_result.status == "completed":
                    successful_steps.append(step_lookup[step_result.step_id])
            if fail_fast and any(item.status == "failed" for item in batch_results):
                if rollback_on_failure:
                    result.rollback_actions.extend(
                        await self._run_rollbacks(
                            successful_steps=successful_steps,
                            registry=registry,
                            context=context,
                            objective=plan.objective,
                            result_map=result_map,
                        )
                    )
                break

        completed_count = sum(1 for item in result.step_results if item.status == "completed")
        failed_count = sum(1 for item in result.step_results if item.status == "failed")
        result.response = f"Execution finished: completed={completed_count}, failed={failed_count}."
        return result

    async def _run_batch(
        self,
        steps: list[PlanStep],
        registry: CapabilityRegistry,
        context: CallContext,
    ) -> list[ExecutionStepResult]:
        ordered_results: dict[str, ExecutionStepResult] = {}

        async def _run(step: PlanStep) -> None:
            ordered_results[step.step_id] = await self._run_step(step, registry, context)

        async with asyncio.TaskGroup() as task_group:
            for step in steps:
                task_group.create_task(_run(step))

        return [ordered_results[step.step_id] for step in steps if step.step_id in ordered_results]

    async def _run_step(
        self,
        step: PlanStep,
        registry: CapabilityRegistry,
        context: CallContext,
    ) -> ExecutionStepResult:
        callable_obj = registry.get_runtime(step.capability_id)
        if not isinstance(callable_obj, IInvocable):
            return ExecutionStepResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=f"Capability {step.capability_id!r} is not executable.",
                execution_target=step.execution_target,
            )

        max_attempts = max(1, step.retry_policy.max_attempts)
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            started = time.monotonic()
            try:
                input_obj = self._build_input(callable_obj.input_schema, step)
                child_context = context.child(callable_obj.name, callable_obj.callable_type)
                invoke_result = await callable_obj.invoke(input_obj, child_context)
                duration_ms = int((time.monotonic() - started) * 1000)
                if invoke_result.success:
                    excerpt = ""
                    if invoke_result.output is not None:
                        excerpt = invoke_result.output.model_dump_json()[:500]
                        # Domain-level failures encoded in output.passed=False
                        # (e.g. quality_gate) must be treated as step failures.
                        if getattr(invoke_result.output, "passed", None) is False:
                            last_error = getattr(
                                invoke_result.output,
                                "summary",
                                f"{step.capability_id} reported passed=False",
                            )
                            continue
                    return ExecutionStepResult(
                        step_id=step.step_id,
                        capability_id=step.capability_id,
                        status="completed",
                        attempts=attempt,
                        dependency_ids=list(step.depends_on),
                        output_excerpt=excerpt,
                        duration_ms=duration_ms,
                        execution_target=step.execution_target,
                    )
                last_error = invoke_result.error.message if invoke_result.error else "Unknown execution error."
            except (CitnegaError, InvalidConfigError) as exc:
                last_error = str(exc)
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_attempts and step.retry_policy.backoff_seconds > 0:
                await asyncio.sleep(step.retry_policy.backoff_seconds)

        return ExecutionStepResult(
            step_id=step.step_id,
            capability_id=step.capability_id,
            status="failed",
            attempts=max_attempts,
            dependency_ids=list(step.depends_on),
            error=last_error,
            execution_target=step.execution_target,
        )

    def _build_input(self, schema: type[BaseModel], step: PlanStep) -> BaseModel:
        payload: dict[str, Any] = dict(step.args)
        if step.task:
            # Always populate "task" as the canonical field; AgentInput aliases handle the rest.
            payload.setdefault("task", step.task)
            # Also set legacy fields if the schema explicitly declares them (backwards compat).
            for candidate in _TEXT_FIELD_CANDIDATES:
                if candidate in getattr(schema, "model_fields", {}):
                    payload.setdefault(candidate, step.task)
        return schema.model_validate(payload)

    async def _run_rollbacks(
        self,
        *,
        successful_steps: list[PlanStep],
        registry: CapabilityRegistry,
        context: CallContext,
        objective: str,
        result_map: dict[str, ExecutionStepResult],
    ) -> list[str]:
        actions: list[str] = []
        for step in reversed(successful_steps):
            rollback_capability_id = step.rollback_capability_id.strip()
            if not rollback_capability_id:
                continue
            rollback_callable = registry.get_runtime(rollback_capability_id)
            if not isinstance(rollback_callable, IInvocable):
                actions.append(
                    f"{step.step_id}: rollback capability {rollback_capability_id!r} is not executable"
                )
                continue

            try:
                rollback_step = step.model_copy(
                    update={
                        "capability_id": rollback_capability_id,
                        "args": dict(step.rollback_args),
                        "task": f"Rollback for {step.step_id}: {step.task or objective}",
                    }
                )
                rollback_input = self._build_input(rollback_callable.input_schema, rollback_step)
                child_context = context.child(rollback_callable.name, rollback_callable.callable_type)
                invoke_result = await rollback_callable.invoke(rollback_input, child_context)
                if invoke_result.success:
                    actions.append(
                        f"{step.step_id}: rollback via '{rollback_capability_id}' succeeded"
                    )
                    if step.step_id in result_map and result_map[step.step_id].status == "completed":
                        result_map[step.step_id].status = "rolled_back"
                else:
                    error = (
                        invoke_result.error.message if invoke_result.error is not None else "unknown failure"
                    )
                    actions.append(
                        f"{step.step_id}: rollback via '{rollback_capability_id}' failed ({error})"
                    )
            except Exception as exc:
                actions.append(
                    f"{step.step_id}: rollback via '{rollback_capability_id}' exception ({exc})"
                )
        return actions

    def _emit_batch_started(
        self,
        plan: CompiledPlan,
        batch: ExecutionBatch,
        context: CallContext,
    ) -> None:
        if self._event_emitter is None:
            return
        from citnega.packages.protocol.events.planning import ExecutionBatchStartedEvent

        self._event_emitter.emit(
            ExecutionBatchStartedEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                plan_id=plan.plan_id,
                batch_id=batch.batch_id,
                step_ids=list(batch.step_ids),
            )
        )

    def _emit_batch_completed(
        self,
        plan: CompiledPlan,
        batch: ExecutionBatch,
        batch_results: list[ExecutionStepResult],
        context: CallContext,
    ) -> None:
        if self._event_emitter is None:
            return
        from citnega.packages.protocol.events.planning import ExecutionBatchCompletedEvent

        self._event_emitter.emit(
            ExecutionBatchCompletedEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                plan_id=plan.plan_id,
                batch_id=batch.batch_id,
                step_ids=list(batch.step_ids),
                statuses=[item.status for item in batch_results],
            )
        )
