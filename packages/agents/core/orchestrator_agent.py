"""
OrchestratorAgent — deterministic DAG-style execution across tools and agents.

Features:
  - Executes user-provided step plans with dependencies.
  - Supports bounded retries per step.
  - Optional rollback hooks when a later step fails.
  - Can auto-generate a plan via model gateway when no steps are supplied.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
import uuid

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IStreamable
    from citnega.packages.runtime.remote.executor import (
        HttpRemoteWorkerPool,
        InProcessRemoteWorkerPool,
    )

_TEXT_FIELD_CANDIDATES = ("task", "query", "goal", "text", "user_input", "prompt")


class OrchestrationStep(BaseModel):
    step_id: str
    callable_name: str
    task: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    retries: int = 0
    rollback_callable: str = ""
    rollback_args: dict[str, Any] = Field(default_factory=dict)
    execution_target: str = Field(
        default="local",
        description="Execution target: local | remote",
    )
    worker_hint: str = Field(
        default="",
        description="Optional worker hint used by remote dispatch.",
    )


class OrchestratorInput(BaseModel):
    goal: str = Field(description="High-level orchestration objective.")
    steps: list[OrchestrationStep] = Field(
        default_factory=list,
        description="Explicit execution plan. If empty, agent may auto-plan.",
    )
    working_dir: str = Field(default="", description="Working directory injected into step inputs.")
    max_steps: int = 10
    max_retries: int = 1
    auto_plan: bool = True
    rollback_on_failure: bool = True
    fail_fast: bool = True
    allow_remote: bool = False


class OrchestrationStepResult(BaseModel):
    step_id: str
    callable_name: str
    status: str
    attempts: int
    dependency_ids: list[str] = Field(default_factory=list)
    output_excerpt: str = ""
    error: str = ""
    duration_ms: int = 0
    execution_target: str = "local"
    worker_id: str = ""
    envelope_id: str = ""
    envelope_verified: bool | None = None


class OrchestratorOutput(BaseModel):
    response: str
    plan: list[str] = Field(default_factory=list)
    step_results: list[OrchestrationStepResult] = Field(default_factory=list)
    completed_steps: int = 0
    failed_steps: int = 0
    rollback_actions: list[str] = Field(default_factory=list)
    generated_plan: bool = False


_PLAN_PROMPT = """\
Create a minimal JSON plan for this goal.
Reply with JSON only, format:
{"steps":[{"step_id":"step1","callable_name":"<name>","task":"<what to do>","depends_on":[]}]}

Available callables:
{menu}

Rules:
- Use at most {max_steps} steps.
- Include dependencies via depends_on.
- Prefer qa_agent, repo_map, test_matrix, quality_gate for QA/architecture tasks.
"""


class OrchestratorAgent(BaseCoreAgent):
    name = "orchestrator_agent"
    description = (
        "Deterministic multi-step orchestrator with dependencies, retries, and rollback hooks. "
        "Use for tasks that require explicit execution plans across multiple tools/agents."
    )
    callable_type = CallableType.CORE
    llm_direct_access: bool = True
    input_schema = OrchestratorInput
    output_schema = OrchestratorOutput
    policy = CallablePolicy(
        timeout_seconds=900.0,
        requires_approval=False,
        network_allowed=True,
        max_depth_allowed=6,
    )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._remote_enabled_default = False
        self._remote_worker_mode = "inprocess"
        self._remote_workers = 2
        self._remote_require_signed_envelopes = True
        self._remote_envelope_signing_key = ""
        self._remote_envelope_signing_key_id = "current"
        self._remote_envelope_verification_keys: tuple[str, ...] = ()
        self._remote_simulate_latency_ms = 0
        self._remote_http_endpoint = ""
        self._remote_request_timeout_ms = 15000
        self._remote_auth_token = ""
        self._remote_verify_tls = True
        self._remote_ca_cert_path = ""
        self._remote_client_cert_path = ""
        self._remote_client_key_path = ""
        self._remote_allowed_callables: frozenset[str] = frozenset()
        self._remote_executor = None
        self._remote_executor_fingerprint = ""

    def configure_remote_execution(self, remote_settings: object) -> None:
        """
        Configure remote execution defaults from app settings.

        ``remote_settings`` is duck-typed so tests can pass a simple stub.
        """
        self._remote_enabled_default = bool(getattr(remote_settings, "enabled", False))
        self._remote_worker_mode = str(
            getattr(remote_settings, "worker_mode", "inprocess")
        ).strip().lower() or "inprocess"
        self._remote_workers = max(1, int(getattr(remote_settings, "workers", 2)))
        self._remote_require_signed_envelopes = bool(
            getattr(remote_settings, "require_signed_envelopes", True)
        )
        self._remote_envelope_signing_key = str(
            getattr(remote_settings, "envelope_signing_key", "")
        ).strip()
        self._remote_envelope_signing_key_id = str(
            getattr(remote_settings, "envelope_signing_key_id", "current")
        ).strip() or "current"
        raw_verification_keys = getattr(remote_settings, "envelope_verification_keys", []) or []
        self._remote_envelope_verification_keys = tuple(
            str(entry).strip() for entry in raw_verification_keys if str(entry).strip()
        )
        self._remote_simulate_latency_ms = max(
            0, int(getattr(remote_settings, "simulate_latency_ms", 0))
        )
        self._remote_http_endpoint = str(
            getattr(remote_settings, "http_endpoint", "")
        ).strip()
        self._remote_request_timeout_ms = max(
            1, int(getattr(remote_settings, "request_timeout_ms", 15000))
        )
        self._remote_auth_token = str(getattr(remote_settings, "auth_token", "")).strip()
        self._remote_verify_tls = bool(getattr(remote_settings, "verify_tls", True))
        self._remote_ca_cert_path = str(getattr(remote_settings, "ca_cert_path", "")).strip()
        self._remote_client_cert_path = str(
            getattr(remote_settings, "client_cert_path", "")
        ).strip()
        self._remote_client_key_path = str(
            getattr(remote_settings, "client_key_path", "")
        ).strip()
        allowed = getattr(remote_settings, "allowed_callables", []) or []
        self._remote_allowed_callables = frozenset(
            str(name).strip() for name in allowed if str(name).strip()
        )
        self._remote_executor = None
        self._remote_executor_fingerprint = ""

    async def _execute(self, input: OrchestratorInput, context: CallContext) -> OrchestratorOutput:
        callables = self._discover_callables()
        steps, generated_plan = await self._resolve_steps(input, callables, context)
        if not steps:
            return OrchestratorOutput(
                response="No executable steps were resolved.",
                generated_plan=generated_plan,
            )

        if self._nextgen_execution_enabled() and all(
            (step.execution_target or "local").strip().lower() == "local"
            for step in steps
        ):
            nextgen_output = await self._execute_via_nextgen_engine(
                input=input,
                steps=steps,
                callables=callables,
                context=context,
                generated_plan=generated_plan,
            )
            if nextgen_output is not None:
                return nextgen_output

        step_results: list[OrchestrationStepResult] = []
        by_id: dict[str, OrchestrationStepResult] = {}
        successful_for_rollback: list[OrchestrationStep] = []
        rollback_actions: list[str] = []

        pending: dict[str, OrchestrationStep] = {s.step_id: s for s in steps}
        abort = False

        while pending and not abort:
            ready: list[OrchestrationStep] = []
            for step in pending.values():
                if all(dep in by_id for dep in step.depends_on):
                    ready.append(step)

            if not ready:
                for step in list(pending.values()):
                    result = OrchestrationStepResult(
                        step_id=step.step_id,
                        callable_name=step.callable_name,
                        status="skipped",
                        attempts=0,
                        dependency_ids=list(step.depends_on),
                        error="Unresolved dependencies (cycle or missing dependency result).",
                    )
                    step_results.append(result)
                    by_id[step.step_id] = result
                    pending.pop(step.step_id, None)
                break

            for step in ready:
                pending.pop(step.step_id, None)
                blocked_deps = [
                    dep
                    for dep in step.depends_on
                    if by_id.get(dep) and by_id[dep].status not in {"completed", "rolled_back"}
                ]
                if blocked_deps:
                    result = OrchestrationStepResult(
                        step_id=step.step_id,
                        callable_name=step.callable_name,
                        status="skipped",
                        attempts=0,
                        dependency_ids=list(step.depends_on),
                        error=f"Blocked by failed/skipped dependencies: {', '.join(blocked_deps)}",
                    )
                    step_results.append(result)
                    by_id[step.step_id] = result
                    continue

                result = await self._run_step(step, input, callables, context)
                step_results.append(result)
                by_id[step.step_id] = result

                if result.status == "completed":
                    successful_for_rollback.append(step)
                    continue

                if input.rollback_on_failure:
                    rollback_actions.extend(
                        await self._run_rollbacks(
                            successful_steps=successful_for_rollback,
                            input=input,
                            callables=callables,
                            context=context,
                            step_results=step_results,
                        )
                    )

                if input.fail_fast:
                    for rem in list(pending.values()):
                        skipped = OrchestrationStepResult(
                            step_id=rem.step_id,
                            callable_name=rem.callable_name,
                            status="skipped",
                            attempts=0,
                            dependency_ids=list(rem.depends_on),
                            error=f"Skipped due to prior failure at step '{step.step_id}'.",
                        )
                        step_results.append(skipped)
                        by_id[rem.step_id] = skipped
                        pending.pop(rem.step_id, None)
                    abort = True
                    break

        completed_steps = sum(1 for r in step_results if r.status == "completed")
        failed_steps = sum(1 for r in step_results if r.status == "failed")
        rolled_back_steps = sum(1 for r in step_results if r.status == "rolled_back")
        plan_lines = [
            f"{s.step_id}: {s.callable_name} ({'deps=' + ','.join(s.depends_on) if s.depends_on else 'deps=none'})"
            for s in steps
        ]
        response = (
            f"Orchestration finished: completed={completed_steps}, "
            f"failed={failed_steps}, rolled_back={rolled_back_steps}, total={len(step_results)}."
        )

        return OrchestratorOutput(
            response=response,
            plan=plan_lines,
            step_results=step_results,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            rollback_actions=rollback_actions,
            generated_plan=generated_plan,
        )

    async def _execute_via_nextgen_engine(
        self,
        *,
        input: OrchestratorInput,
        steps: list[OrchestrationStep],
        callables: dict[str, IStreamable],
        context: CallContext,
        generated_plan: bool,
    ) -> OrchestratorOutput | None:
        from citnega.packages.capabilities import BuiltinCapabilityProvider, CapabilityRegistry
        from citnega.packages.execution import ExecutionEngine
        from citnega.packages.planning import (
            CompiledPlan,
            PlanStep,
            PlanStepType,
            PlanValidator,
            RetryPolicy,
        )
        from citnega.packages.protocol.events.planning import PlanCompiledEvent, PlanValidatedEvent

        registry = CapabilityRegistry()
        records, diagnostics = BuiltinCapabilityProvider().load(callables)
        if diagnostics.has_required_failures:
            return None
        registry.register_many(records, overwrite=True)

        plan_steps: list[PlanStep] = []
        for step in steps:
            descriptor = registry.get_descriptor(step.callable_name)
            if descriptor is None:
                return None
            plan_steps.append(
                PlanStep(
                    step_id=step.step_id,
                    step_type=(
                        PlanStepType.AGENT
                        if descriptor.kind.value == "agent"
                        else PlanStepType.TOOL
                    ),
                    capability_id=step.callable_name,
                    args=self._build_payload(
                        schema=callables[step.callable_name].input_schema,
                        goal=input.goal,
                        task=step.task,
                        args=step.args,
                        working_dir=input.working_dir,
                    ),
                    task=step.task or input.goal,
                    depends_on=list(step.depends_on),
                    can_run_in_parallel=descriptor.execution_traits.parallel_safe,
                    retry_policy=RetryPolicy(
                        max_attempts=max(1, (step.retries if step.retries > 0 else input.max_retries) + 1)
                    ),
                    rollback_capability_id=step.rollback_callable,
                    rollback_args=dict(step.rollback_args),
                    execution_target="local",
                )
            )

        compiled_plan = CompiledPlan(
            plan_id=f"orchestrated-{uuid.uuid4()}",
            objective=input.goal,
            steps=plan_steps,
            generated_from="orchestrator_agent",
            max_parallelism=max(1, len(plan_steps)),
            metadata={"allow_remote": input.allow_remote, "generated_plan": generated_plan},
        )
        validation = PlanValidator().validate(compiled_plan, registry)
        self._event_emitter.emit(
            PlanCompiledEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                callable_name=self.name,
                callable_type=self.callable_type,
                plan_id=compiled_plan.plan_id,
                objective=compiled_plan.objective,
                generated_from=compiled_plan.generated_from,
                step_count=len(compiled_plan.steps),
            )
        )
        self._event_emitter.emit(
            PlanValidatedEvent(
                session_id=context.session_id,
                run_id=context.run_id,
                turn_id=context.turn_id,
                callable_name=self.name,
                callable_type=self.callable_type,
                plan_id=compiled_plan.plan_id,
                valid=validation.valid,
                errors=validation.errors,
            )
        )
        if not validation.valid:
            return None

        engine = ExecutionEngine(event_emitter=self._event_emitter)
        execution_result = await engine.execute(
            compiled_plan,
            registry,
            context.child(self.name, self.callable_type),
            fail_fast=input.fail_fast,
            rollback_on_failure=input.rollback_on_failure,
        )
        step_results = [
            OrchestrationStepResult(
                step_id=item.step_id,
                callable_name=item.capability_id,
                status=item.status,
                attempts=item.attempts,
                dependency_ids=list(item.dependency_ids),
                output_excerpt=item.output_excerpt,
                error=item.error,
                duration_ms=item.duration_ms,
                execution_target=item.execution_target,
            )
            for item in execution_result.step_results
        ]
        return OrchestratorOutput(
            response=execution_result.response,
            plan=[
                f"{step.step_id}: {step.callable_name} "
                f"({'deps=' + ','.join(step.depends_on) if step.depends_on else 'deps=none'})"
                for step in steps
            ],
            step_results=step_results,
            completed_steps=sum(1 for item in step_results if item.status == "completed"),
            failed_steps=sum(1 for item in step_results if item.status == "failed"),
            rollback_actions=list(execution_result.rollback_actions),
            generated_plan=generated_plan,
        )

    def _discover_callables(self) -> dict[str, IStreamable]:
        callables: dict[str, IStreamable] = {}

        for name, obj in self._tool_registry.items():
            callables[name] = obj

        for peer in self.list_sub_callables():
            if peer.name in {self.name, "router_agent", "conversation_agent"}:
                continue
            callables[peer.name] = peer

        return callables

    async def _resolve_steps(
        self,
        input: OrchestratorInput,
        callables: dict[str, IStreamable],
        context: CallContext,
    ) -> tuple[list[OrchestrationStep], bool]:
        if input.steps:
            return self._normalise_steps(input.steps, input.max_steps), False

        if not input.auto_plan:
            return self._fallback_steps(input.goal, callables), False

        if context.model_gateway is None:
            return self._fallback_steps(input.goal, callables), False

        try:
            from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

            menu = "\n".join(
                f"- {name}: {getattr(obj, 'description', '')[:120]}"
                for name, obj in sorted(callables.items())
            )
            prompt = _PLAN_PROMPT.format(menu=menu or "- qa_agent", max_steps=max(1, input.max_steps))
            response = await context.model_gateway.generate(
                ModelRequest(
                    messages=[
                        ModelMessage(role="system", content=prompt),
                        ModelMessage(role="user", content=f"Goal: {input.goal}"),
                    ],
                    stream=False,
                    temperature=0.0,
                )
            )
            raw = response.content.strip()
            data = json.loads(raw)
            raw_steps = data.get("steps", data if isinstance(data, list) else [])
            steps = [OrchestrationStep.model_validate(s) for s in raw_steps]
            if steps:
                return self._normalise_steps(steps, input.max_steps), True
        except Exception:
            pass

        return self._fallback_steps(input.goal, callables), True

    def _normalise_steps(self, steps: list[OrchestrationStep], max_steps: int) -> list[OrchestrationStep]:
        seen: set[str] = set()
        out: list[OrchestrationStep] = []
        for idx, step in enumerate(steps[: max(1, max_steps)], start=1):
            sid = step.step_id.strip() or f"step{idx}"
            if sid in seen:
                sid = f"{sid}_{idx}"
            seen.add(sid)
            out.append(step.model_copy(update={"step_id": sid}))
        return out

    def _fallback_steps(
        self,
        goal: str,
        callables: dict[str, IStreamable],
    ) -> list[OrchestrationStep]:
        for candidate in ("qa_agent", "planner_agent", "research_agent", "reasoning_agent"):
            if candidate in callables:
                return [OrchestrationStep(step_id="step1", callable_name=candidate, task=goal)]
        for name in callables:
            return [OrchestrationStep(step_id="step1", callable_name=name, task=goal)]
        return []

    async def _run_step(
        self,
        step: OrchestrationStep,
        input: OrchestratorInput,
        callables: dict[str, IStreamable],
        context: CallContext,
    ) -> OrchestrationStepResult:
        execution_target = (step.execution_target or "local").strip().lower()
        if execution_target not in {"local", "remote"}:
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=f"Unsupported execution_target={step.execution_target!r}. Expected local|remote.",
                execution_target=execution_target,
            )

        if execution_target == "remote":
            return await self._run_step_remote(step, input, callables, context)

        target = callables.get(step.callable_name)
        if target is None:
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=f"Callable not found: {step.callable_name}",
                execution_target="local",
            )

        retries = max(0, step.retries if step.retries > 0 else input.max_retries)
        max_attempts = retries + 1
        last_error = ""
        started = time.monotonic()

        for attempt in range(1, max_attempts + 1):
            try:
                payload = self._build_payload(
                    schema=target.input_schema,
                    goal=input.goal,
                    task=step.task,
                    args=step.args,
                    working_dir=input.working_dir,
                )
                input_obj = target.input_schema.model_validate(payload)
                child_ctx = context.child(self.name, self.callable_type)
                result = await target.invoke(input_obj, child_ctx)
                if result.success and result.output:
                    # Some orchestration-oriented tools (e.g. quality_gate) encode
                    # domain failure inside output.passed=False while still returning
                    # a successful invocation envelope.
                    output_passed = getattr(result.output, "passed", None)
                    if output_passed is False:
                        last_error = getattr(
                            result.output,
                            "summary",
                            f"{step.callable_name} reported passed=false",
                        )
                        continue
                    return OrchestrationStepResult(
                        step_id=step.step_id,
                        callable_name=step.callable_name,
                        status="completed",
                        attempts=attempt,
                        dependency_ids=list(step.depends_on),
                        output_excerpt=self._output_excerpt(result.output),
                        duration_ms=int((time.monotonic() - started) * 1000),
                        execution_target="local",
                    )
                if result.error is not None:
                    last_error = result.error.message
                else:
                    last_error = "Invocation failed with unknown error."
            except Exception as exc:
                last_error = str(exc)

        return OrchestrationStepResult(
            step_id=step.step_id,
            callable_name=step.callable_name,
            status="failed",
            attempts=max_attempts,
            dependency_ids=list(step.depends_on),
            error=last_error or "Step failed.",
            duration_ms=int((time.monotonic() - started) * 1000),
            execution_target="local",
        )

    async def _run_step_remote(
        self,
        step: OrchestrationStep,
        input: OrchestratorInput,
        callables: dict[str, IStreamable],
        context: CallContext,
    ) -> OrchestrationStepResult:
        from citnega.packages.protocol.events.remote import RemoteExecutionEvent

        target = callables.get(step.callable_name)
        if target is None:
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=f"Callable not found: {step.callable_name}",
                execution_target="remote",
            )

        if not (input.allow_remote or self._remote_enabled_default):
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=(
                    "Remote execution requested but disabled. Set allow_remote=true "
                    "or enable [remote].enabled in settings."
                ),
                execution_target="remote",
            )

        if (
            self._remote_allowed_callables
            and step.callable_name not in self._remote_allowed_callables
        ):
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=f"Callable {step.callable_name!r} is not allowed for remote execution.",
                execution_target="remote",
            )

        if self._remote_worker_mode not in {"inprocess", "http"}:
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=(
                    f"Unsupported remote worker mode: {self._remote_worker_mode!r}. "
                    "Currently supported: 'inprocess', 'http'."
                ),
                execution_target="remote",
            )

        try:
            remote_executor = self._get_remote_executor()
        except Exception as exc:
            return OrchestrationStepResult(
                step_id=step.step_id,
                callable_name=step.callable_name,
                status="failed",
                attempts=0,
                dependency_ids=list(step.depends_on),
                error=str(exc),
                execution_target="remote",
            )

        retries = max(0, step.retries if step.retries > 0 else input.max_retries)
        max_attempts = retries + 1
        last_error = ""
        last_worker_id = ""
        last_envelope_id = ""
        last_verified: bool | None = None
        started = time.monotonic()

        for attempt in range(1, max_attempts + 1):
            try:
                payload = self._build_payload(
                    schema=target.input_schema,
                    goal=input.goal,
                    task=step.task,
                    args=step.args,
                    working_dir=input.working_dir,
                )
                input_obj = target.input_schema.model_validate(payload)
                child_ctx = context.child(self.name, self.callable_type)

                self._event_emitter.emit(
                    RemoteExecutionEvent(
                        session_id=context.session_id,
                        run_id=context.run_id,
                        turn_id=context.turn_id,
                        callable_name=self.name,
                        callable_type=self.callable_type,
                        phase="dispatch",
                        target_callable=step.callable_name,
                        verification_result="skipped",
                        details=f"attempt={attempt}",
                    )
                )

                result, dispatch = await remote_executor.invoke(
                    target=target,
                    input_obj=input_obj,
                    context=child_ctx,
                    parent_callable=self.name,
                    attempt=attempt,
                    worker_hint=step.worker_hint,
                )
                last_worker_id = dispatch.worker_id
                last_envelope_id = dispatch.envelope.envelope_id
                last_verified = dispatch.verification.ok

                self._event_emitter.emit(
                    RemoteExecutionEvent(
                        session_id=context.session_id,
                        run_id=context.run_id,
                        turn_id=context.turn_id,
                        callable_name=self.name,
                        callable_type=self.callable_type,
                        phase="verified",
                        worker_id=dispatch.worker_id,
                        envelope_id=dispatch.envelope.envelope_id,
                        target_callable=step.callable_name,
                        verification_result=(
                            "verified" if dispatch.verification.ok else "failed"
                        ),
                        details=dispatch.verification.reason,
                    )
                )

                if result.success and result.output:
                    output_passed = getattr(result.output, "passed", None)
                    if output_passed is False:
                        last_error = getattr(
                            result.output,
                            "summary",
                            f"{step.callable_name} reported passed=false",
                        )
                        continue

                    self._event_emitter.emit(
                        RemoteExecutionEvent(
                            session_id=context.session_id,
                            run_id=context.run_id,
                            turn_id=context.turn_id,
                            callable_name=self.name,
                            callable_type=self.callable_type,
                            phase="complete",
                            worker_id=dispatch.worker_id,
                            envelope_id=dispatch.envelope.envelope_id,
                            target_callable=step.callable_name,
                            verification_result="verified",
                            details="remote dispatch completed",
                        )
                    )
                    return OrchestrationStepResult(
                        step_id=step.step_id,
                        callable_name=step.callable_name,
                        status="completed",
                        attempts=attempt,
                        dependency_ids=list(step.depends_on),
                        output_excerpt=self._output_excerpt(result.output),
                        duration_ms=int((time.monotonic() - started) * 1000),
                        execution_target="remote",
                        worker_id=dispatch.worker_id,
                        envelope_id=dispatch.envelope.envelope_id,
                        envelope_verified=dispatch.verification.ok,
                    )

                if result.error is not None:
                    last_error = result.error.message
                else:
                    last_error = "Remote invocation failed with unknown error."
            except Exception as exc:
                last_error = str(exc)

        return OrchestrationStepResult(
            step_id=step.step_id,
            callable_name=step.callable_name,
            status="failed",
            attempts=max_attempts,
            dependency_ids=list(step.depends_on),
            error=last_error or "Remote step failed.",
            duration_ms=int((time.monotonic() - started) * 1000),
            execution_target="remote",
            worker_id=last_worker_id,
            envelope_id=last_envelope_id,
            envelope_verified=last_verified,
        )

    def _get_remote_executor(self) -> InProcessRemoteWorkerPool | HttpRemoteWorkerPool:
        from citnega.packages.runtime.remote.executor import (
            HttpRemoteWorkerPool,
            InProcessRemoteWorkerPool,
        )

        fingerprint = "|".join(
            [
                self._remote_worker_mode,
                str(self._remote_workers),
                str(self._remote_require_signed_envelopes),
                self._remote_envelope_signing_key,
                self._remote_envelope_signing_key_id,
                json.dumps(self._remote_envelope_verification_keys),
                str(self._remote_simulate_latency_ms),
                self._remote_http_endpoint,
                str(self._remote_request_timeout_ms),
                self._remote_auth_token,
                str(self._remote_verify_tls),
                self._remote_ca_cert_path,
                self._remote_client_cert_path,
                self._remote_client_key_path,
            ]
        )
        if self._remote_executor is None or self._remote_executor_fingerprint != fingerprint:
            if self._remote_worker_mode == "http":
                self._remote_executor = HttpRemoteWorkerPool(
                    endpoint=self._remote_http_endpoint,
                    signing_key=self._remote_envelope_signing_key,
                    signing_key_id=self._remote_envelope_signing_key_id,
                    verification_keys=self._remote_envelope_verification_keys,
                    require_signed_envelopes=self._remote_require_signed_envelopes,
                    timeout_ms=self._remote_request_timeout_ms,
                    auth_token=self._remote_auth_token,
                    verify_tls=self._remote_verify_tls,
                    ca_cert_path=self._remote_ca_cert_path,
                    client_cert_path=self._remote_client_cert_path,
                    client_key_path=self._remote_client_key_path,
                )
            else:
                self._remote_executor = InProcessRemoteWorkerPool(
                    workers=self._remote_workers,
                    signing_key=self._remote_envelope_signing_key,
                    signing_key_id=self._remote_envelope_signing_key_id,
                    verification_keys=self._remote_envelope_verification_keys,
                    require_signed_envelopes=self._remote_require_signed_envelopes,
                    simulate_latency_ms=self._remote_simulate_latency_ms,
                )
            self._remote_executor_fingerprint = fingerprint
        return self._remote_executor

    async def _run_rollbacks(
        self,
        *,
        successful_steps: list[OrchestrationStep],
        input: OrchestratorInput,
        callables: dict[str, IStreamable],
        context: CallContext,
        step_results: list[OrchestrationStepResult],
    ) -> list[str]:
        actions: list[str] = []
        by_step_id = {r.step_id: r for r in step_results}

        for step in reversed(successful_steps):
            rollback_name = step.rollback_callable.strip()
            if not rollback_name:
                continue
            target = callables.get(rollback_name)
            if target is None:
                actions.append(f"{step.step_id}: rollback callable '{rollback_name}' not found")
                continue

            try:
                rollback_task = f"Rollback for {step.step_id}: {step.task or input.goal}"
                payload = self._build_payload(
                    schema=target.input_schema,
                    goal=input.goal,
                    task=rollback_task,
                    args=step.rollback_args,
                    working_dir=input.working_dir,
                )
                input_obj = target.input_schema.model_validate(payload)
                child_ctx = context.child(self.name, self.callable_type)
                result = await target.invoke(input_obj, child_ctx)
                if result.success:
                    actions.append(f"{step.step_id}: rollback via '{rollback_name}' succeeded")
                    existing = by_step_id.get(step.step_id)
                    if existing and existing.status == "completed":
                        existing.status = "rolled_back"
                else:
                    msg = result.error.message if result.error else "unknown failure"
                    actions.append(f"{step.step_id}: rollback via '{rollback_name}' failed ({msg})")
            except Exception as exc:
                actions.append(f"{step.step_id}: rollback via '{rollback_name}' exception ({exc})")

        return actions

    def _build_payload(
        self,
        *,
        schema: type,
        goal: str,
        task: str,
        args: dict[str, Any],
        working_dir: str,
    ) -> dict[str, Any]:
        payload = dict(args)
        fields = getattr(schema, "model_fields", {})

        if working_dir:
            for key in ("working_dir", "root_path", "dir_path"):
                if key in fields and key not in payload:
                    payload[key] = working_dir

        text_val = task or goal
        if text_val:
            for candidate in _TEXT_FIELD_CANDIDATES:
                if candidate in fields and candidate not in payload:
                    payload[candidate] = text_val
                    break

        if "goal" in fields and "goal" not in payload:
            payload["goal"] = goal

        for name, f in fields.items():
            if name in payload:
                continue
            if f.is_required():
                annotation = f.annotation
                if annotation in (str, "str"):
                    payload[name] = text_val

        return payload

    def _output_excerpt(self, output: BaseModel) -> str:
        for field in ("response", "result", "summary", "content", "output"):
            value = getattr(output, field, None)
            if value:
                text = str(value)
                return text[:280]
        return output.model_dump_json()[:280]

    @staticmethod
    def _nextgen_execution_enabled() -> bool:
        try:
            from citnega.packages.config.loaders import load_settings

            return load_settings().nextgen.execution_enabled
        except Exception:
            return False
