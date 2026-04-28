from __future__ import annotations

import asyncio
import random
import re
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from citnega.packages.capabilities.registry import CapabilityRegistry
from citnega.packages.execution.models import ExecutionBatch, ExecutionResult, ExecutionStepResult
from citnega.packages.execution.scheduler import PlanScheduler
from citnega.packages.planning.models import CompiledPlan, PlanStep, PlanStepType
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.shared.errors import CitnegaError, InvalidConfigError

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.events import IEventEmitter

_TEXT_FIELD_CANDIDATES = ("task", "query", "goal", "text", "user_input", "prompt", "objective")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\.result\}")


class ExecutionEngine:
    def __init__(
        self,
        scheduler: PlanScheduler | None = None,
        *,
        event_emitter: IEventEmitter | None = None,
    ) -> None:
        self._scheduler = scheduler or PlanScheduler()
        self._event_emitter = event_emitter
        self._idempotency_cache: dict[str, ExecutionStepResult] = {}

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
            batch_results = await self._run_batch(pending_steps, registry, context, completed_results=result_map)
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

            # Check stop_conditions after each batch
            if plan.stop_conditions:
                from citnega.packages.shared.safe_eval import safe_eval
                failed_count = sum(1 for r in result.step_results if r.status == "failed")
                stop_ctx: dict[str, Any] = {
                    sid: sr.output_excerpt for sid, sr in result_map.items()
                }
                stop_ctx["failed_count"] = failed_count
                for cond in plan.stop_conditions:
                    if safe_eval(cond, stop_ctx):
                        completed_count = sum(1 for r in result.step_results if r.status == "completed")
                        result.response = (
                            f"Stopped early: condition '{cond}' met. "
                            f"completed={completed_count}, failed={failed_count}."
                        )
                        return result

        completed_count = sum(1 for item in result.step_results if item.status == "completed")
        failed_count = sum(1 for item in result.step_results if item.status == "failed")
        result.response = f"Execution finished: completed={completed_count}, failed={failed_count}."
        return result

    async def _run_batch(
        self,
        steps: list[PlanStep],
        registry: CapabilityRegistry,
        context: CallContext,
        *,
        completed_results: dict[str, ExecutionStepResult] | None = None,
    ) -> list[ExecutionStepResult]:
        ordered_results: dict[str, ExecutionStepResult] = {}

        async def _run(step: PlanStep) -> None:
            ordered_results[step.step_id] = await self._run_step(
                step, registry, context, completed_results=completed_results or {}
            )

        async with asyncio.TaskGroup() as task_group:
            for step in steps:
                task_group.create_task(_run(step))

        return [ordered_results[step.step_id] for step in steps if step.step_id in ordered_results]

    async def _run_step(
        self,
        step: PlanStep,
        registry: CapabilityRegistry,
        context: CallContext,
        *,
        completed_results: dict[str, ExecutionStepResult] | None = None,
    ) -> ExecutionStepResult:
        completed_results = completed_results or {}

        # Condition guard — skip step if expression evaluates to False
        if step.condition:
            from citnega.packages.shared.safe_eval import safe_eval
            cond_ctx = {sid: sr.output_excerpt for sid, sr in completed_results.items()}
            if not safe_eval(step.condition, cond_ctx):
                return ExecutionStepResult(
                    step_id=step.step_id,
                    capability_id=step.capability_id,
                    status="skipped",
                    attempts=0,
                    dependency_ids=list(step.depends_on),
                    execution_target=step.execution_target,
                )

        # APPROVAL_GATE is a meta-step handled inline
        if step.step_type == PlanStepType.APPROVAL_GATE:
            return await self._run_approval_gate(step, context)

        # Idempotency: return cached result if key already seen
        if step.idempotency_key:
            cached = self._idempotency_cache.get(step.idempotency_key)
            if cached is not None:
                return cached

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
                input_obj = self._build_input(callable_obj.input_schema, step, completed_results)
                child_context = context.child(callable_obj.name, callable_obj.callable_type)
                invoke_result = await callable_obj.invoke(input_obj, child_context)
                duration_ms = int((time.monotonic() - started) * 1000)
                if invoke_result.success:
                    excerpt = ""
                    if invoke_result.output is not None:
                        for _f in ("response", "result", "content", "summary", "output"):
                            _v = getattr(invoke_result.output, _f, None)
                            if _v and isinstance(_v, str) and _v.strip():
                                excerpt = _v[:4096]
                                break
                        if not excerpt:
                            excerpt = invoke_result.output.model_dump_json()[:500]
                        if getattr(invoke_result.output, "passed", None) is False:
                            last_error = getattr(
                                invoke_result.output,
                                "summary",
                                f"{step.capability_id} reported passed=False",
                            )
                            continue
                    step_result = ExecutionStepResult(
                        step_id=step.step_id,
                        capability_id=step.capability_id,
                        status="completed",
                        attempts=attempt,
                        dependency_ids=list(step.depends_on),
                        output_excerpt=excerpt,
                        duration_ms=duration_ms,
                        execution_target=step.execution_target,
                    )
                    if step.idempotency_key:
                        self._idempotency_cache[step.idempotency_key] = step_result
                    return step_result
                last_error = invoke_result.error.message if invoke_result.error else "Unknown execution error."
            except (CitnegaError, InvalidConfigError) as exc:
                last_error = str(exc)
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_attempts:
                delay = step.retry_policy.backoff_seconds * (
                    step.retry_policy.backoff_multiplier ** (attempt - 1)
                )
                if step.retry_policy.jitter:
                    delay += random.random()
                if delay > 0:
                    await asyncio.sleep(delay)

        return ExecutionStepResult(
            step_id=step.step_id,
            capability_id=step.capability_id,
            status="failed",
            attempts=max_attempts,
            dependency_ids=list(step.depends_on),
            error=last_error,
            execution_target=step.execution_target,
        )

    async def _run_approval_gate(self, step: PlanStep, context: CallContext) -> ExecutionStepResult:
        approval_manager = getattr(context, "approval_manager", None)
        if approval_manager is None:
            return ExecutionStepResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                status="skipped",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error="approval_manager not available — gate skipped",
                execution_target=step.execution_target,
            )

        try:
            from citnega.packages.protocol.events.planning import ApprovalRequestEvent
            approval_id = f"{step.step_id}-{context.run_id}"
            self._event_emitter and self._event_emitter.emit(
                ApprovalRequestEvent(
                    session_id=context.session_id,
                    run_id=context.run_id,
                    turn_id=context.turn_id,
                    approval_id=approval_id,
                    step_id=step.step_id,
                    message=step.task or f"Approval required for step {step.step_id}",
                )
            )
            approved = await approval_manager.wait_for_response(
                approval_id,
                timeout=step.timeout_policy.timeout_seconds or 300.0,
            )
        except Exception as exc:
            approved = False
            _ = exc

        status = "completed" if approved else "skipped"
        return ExecutionStepResult(
            step_id=step.step_id,
            capability_id=step.capability_id,
            status=status,
            attempts=1,
            dependency_ids=list(step.depends_on),
            execution_target=step.execution_target,
        )

    def _build_input(
        self,
        schema: type[BaseModel],
        step: PlanStep,
        completed_results: dict[str, ExecutionStepResult] | None = None,
    ) -> BaseModel:
        completed_results = completed_results or {}
        payload: dict[str, Any] = dict(step.args)
        if step.task:
            payload.setdefault("task", step.task)
            for candidate in _TEXT_FIELD_CANDIDATES:
                if candidate in getattr(schema, "model_fields", {}):
                    payload.setdefault(candidate, step.task)

        # Substitute {step_id.result} placeholders with output_excerpt from completed steps
        for k, v in list(payload.items()):
            if isinstance(v, str):
                payload[k] = _PLACEHOLDER_RE.sub(
                    lambda m: completed_results.get(m.group(1), ExecutionStepResult(
                        step_id=m.group(1), capability_id="", status="skipped",
                        attempts=0, dependency_ids=[],
                    )).output_excerpt or m.group(0),
                    v,
                )

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
