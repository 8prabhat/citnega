from __future__ import annotations

from typing import TYPE_CHECKING, Any
import uuid

from citnega.packages.planning.models import (
    CompiledPlan,
    PlanStep,
    PlanStepType,
    RetryPolicy,
    WorkflowTemplate,
)
from citnega.packages.planning.workflows import render_template_value
from citnega.packages.strategy.models import StrategySpec

if TYPE_CHECKING:
    from citnega.packages.protocol.events.emitter import EventEmitter


class PlanCompiler:
    def compile_goal(
        self,
        objective: str,
        *,
        strategy: StrategySpec | None = None,
        capability_id: str = "conversation_agent",
        args: dict[str, Any] | None = None,
    ) -> CompiledPlan:
        strategy = strategy or StrategySpec(objective=objective)
        return CompiledPlan(
            plan_id=str(uuid.uuid4()),
            objective=objective,
            generated_from="goal",
            max_parallelism=max(1, strategy.parallelism_budget),
            metadata={
                "active_skills": list(strategy.active_skills),
                "risk_posture": strategy.risk_posture,
            },
            steps=[
                PlanStep(
                    step_id="step1",
                    step_type=PlanStepType.AGENT,
                    capability_id=capability_id,
                    args=args or {"user_input": objective, "goal": objective, "task": objective},
                    task=objective,
                    can_run_in_parallel=False,
                    retry_policy=RetryPolicy(max_attempts=1),
                )
            ],
        )

    def compile_workflow(
        self,
        template: WorkflowTemplate,
        *,
        variables: dict[str, Any] | None = None,
        strategy: StrategySpec | None = None,
        objective: str = "",
        emitter: EventEmitter | None = None,
        session_id: str = "",
        run_id: str = "",
    ) -> CompiledPlan:
        strategy = strategy or StrategySpec(objective=objective or template.description)
        rendered_variables = variables or {}
        steps: list[PlanStep] = []
        for template_step in template.steps:
            steps.append(
                PlanStep(
                    step_id=template_step.step_id,
                    step_type=self._infer_step_type(template_step.capability_id),
                    capability_id=template_step.capability_id,
                    args=render_template_value(template_step.args, rendered_variables),
                    task=str(render_template_value(template_step.task, rendered_variables)),
                    depends_on=list(template_step.depends_on),
                    can_run_in_parallel=template_step.can_run_in_parallel,
                    execution_target=template_step.execution_target,
                )
            )
        plan = CompiledPlan(
            plan_id=str(uuid.uuid4()),
            objective=objective or template.description,
            steps=steps,
            generated_from=f"workflow:{template.name}",
            max_parallelism=max(1, template.max_parallelism, strategy.parallelism_budget),
            metadata={
                "workflow_template": template.name,
                "active_skills": list(strategy.active_skills),
            },
        )
        if emitter is not None:
            try:
                from citnega.packages.protocol.events.planning import WorkflowTemplateExpandedEvent

                emitter.emit(
                    WorkflowTemplateExpandedEvent(
                        session_id=session_id,
                        run_id=run_id,
                        workflow_name=template.name,
                        plan_id=plan.plan_id,
                        step_count=len(steps),
                    )
                )
            except Exception:
                pass
        return plan

    @staticmethod
    def _infer_step_type(capability_id: str) -> PlanStepType:
        return PlanStepType.AGENT if capability_id.endswith("_agent") else PlanStepType.TOOL
