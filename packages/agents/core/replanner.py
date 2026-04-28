"""
RePlanner — adaptive replanning when an execution step fails.

Given:
  • The original goal
  • The steps that succeeded so far
  • The step that just failed and its error
  • The remaining steps that were planned

Produces a revised continuation plan (replacement steps) so the orchestrator
can resume execution without restarting from scratch.

Integrated by OrchestratorAgent when rollback_on_failure=False and
fail_fast=False — the orchestrator calls RePlanner instead of aborting.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class FailedStep(BaseModel):
    step_id: str
    callable_name: str
    task: str
    error: str
    attempts: int


class CompletedStep(BaseModel):
    step_id: str
    callable_name: str
    task: str
    output_excerpt: str = ""


class ReplannerInput(BaseModel):
    goal: str = Field(description="The original high-level goal.")
    completed_steps: list[CompletedStep] = Field(
        default_factory=list,
        description="Steps that succeeded before the failure.",
    )
    failed_step: FailedStep = Field(description="The step that failed.")
    remaining_steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Steps that had not yet run (raw dicts).",
    )
    available_callables: list[str] = Field(
        default_factory=list,
        description="Names of callables available for the revised plan.",
    )
    max_new_steps: int = Field(default=4, description="Max replacement steps to generate.")


class RevisedStep(BaseModel):
    step_id: str
    callable_name: str
    task: str
    depends_on: list[str] = Field(default_factory=list)
    args: dict[str, Any] = Field(default_factory=dict)


class ReplannerOutput(BaseModel):
    revised_steps: list[RevisedStep] = Field(
        description="Replacement steps for the failed + remaining steps.",
    )
    rationale: str = Field(description="One-sentence explanation of the replanning decision.")
    abandon: bool = Field(
        default=False,
        description="True when the goal is unachievable even after replanning.",
    )


_SYSTEM_PROMPT = """\
You are a replanning assistant. A multi-step execution plan has partially failed.
Your job is to generate a revised continuation plan from the point of failure onward.

You will be given:
- The original goal
- Completed steps (with their outputs)
- The failed step (with its error)
- The remaining planned steps
- Available callables

Produce a revised plan that either:
  (a) Retries the failed step with a different callable or approach, or
  (b) Skips the failed step and continues with modified remaining steps, or
  (c) Introduces new intermediate steps to work around the failure.

Reply ONLY with valid JSON (no markdown fences):
{
  "revised_steps": [
    {"step_id": "replan_1", "callable_name": "<name>", "task": "<description>",
     "depends_on": [], "args": {}}
  ],
  "rationale": "<one sentence>",
  "abandon": false
}

If the goal truly cannot be achieved (e.g. required external service unavailable),
set "abandon": true and "revised_steps": [].
"""


class RePlanner(BaseCoreAgent):
    name = "replanner"
    description = (
        "Adaptive replanning agent. Called when an orchestration step fails to generate "
        "a revised continuation plan instead of aborting the entire workflow. "
        "Enables resilient, self-healing multi-step execution."
    )
    callable_type = CallableType.CORE
    llm_direct_access: bool = False  # invoked programmatically by OrchestratorAgent
    input_schema = ReplannerInput
    output_schema = ReplannerOutput
    policy = CallablePolicy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
        max_depth_allowed=2,
    )

    async def _execute(self, input: ReplannerInput, context: CallContext) -> ReplannerOutput:
        if context.model_gateway is None:
            return self._heuristic_replan(input)

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        payload = {
            "goal": input.goal,
            "completed_steps": [s.model_dump() for s in input.completed_steps],
            "failed_step": input.failed_step.model_dump(),
            "remaining_steps": input.remaining_steps,
            "available_callables": input.available_callables,
            "max_new_steps": input.max_new_steps,
        }

        try:
            response = await context.model_gateway.generate(
                ModelRequest(
                    messages=[
                        ModelMessage(role="system", content=_SYSTEM_PROMPT),
                        ModelMessage(
                            role="user",
                            content=json.dumps(payload, indent=2),
                        ),
                    ],
                    stream=False,
                    temperature=0.2,
                )
            )
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())

            revised = [RevisedStep.model_validate(s) for s in data.get("revised_steps", [])]
            return ReplannerOutput(
                revised_steps=revised[: input.max_new_steps],
                rationale=str(data.get("rationale", "")),
                abandon=bool(data.get("abandon", False)),
            )
        except Exception:
            return self._heuristic_replan(input)

    # ── Heuristic fallback (no LLM) ───────────────────────────────────────────

    def _heuristic_replan(self, input: ReplannerInput) -> ReplannerOutput:
        """
        Simple heuristic: if there's an alternative callable, retry with it;
        otherwise skip the failed step and keep the remaining steps.
        """
        failed = input.failed_step
        callables = set(input.available_callables)

        # Try a known fallback mapping
        _FALLBACKS: dict[str, list[str]] = {
            "research_agent":   ["web_search", "search_web", "conversation_agent"],
            "code_agent":       ["conversation_agent"],
            "qa_agent":         ["validator", "conversation_agent"],
            "file_agent":       ["conversation_agent"],
            "data_agent":       ["analysis_agent", "conversation_agent"],
        }
        alternatives = [
            c for c in _FALLBACKS.get(failed.callable_name, [])
            if c in callables and c != failed.callable_name
        ]

        revised: list[RevisedStep] = []
        if alternatives:
            revised.append(
                RevisedStep(
                    step_id=f"replan_{failed.step_id}",
                    callable_name=alternatives[0],
                    task=failed.task,
                    depends_on=[s.step_id for s in input.completed_steps[-1:]],
                )
            )
            rationale = (
                f"Retrying failed step '{failed.step_id}' with '{alternatives[0]}' "
                f"after '{failed.callable_name}' errored."
            )
        else:
            # Skip failed step, carry remaining steps as-is
            for raw_step in input.remaining_steps[: input.max_new_steps]:
                try:
                    revised.append(RevisedStep.model_validate(raw_step))
                except Exception:
                    pass
            rationale = (
                f"Skipping failed step '{failed.step_id}' "
                f"(no alternative for '{failed.callable_name}'), continuing with remaining steps."
            )

        return ReplannerOutput(revised_steps=revised, rationale=rationale, abandon=False)
