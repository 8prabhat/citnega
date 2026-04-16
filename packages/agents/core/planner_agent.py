"""
PlannerAgent — LLM-driven multi-step planning and orchestration core agent.

Unlike ConversationAgent (keyword routing), PlannerAgent asks the model
to decompose a complex task into steps and then executes each step by
delegating to the appropriate specialist or tool.

Plan format (from model):
  STEP 1: <specialist_name> | <task_description>
  STEP 2: <specialist_name> | <task_description>
  ...
  DONE

Each step is executed sequentially; the final response is a synthesis
of all step outputs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class PlannerInput(BaseModel):
    goal: str = Field(description="High-level goal or complex task.")
    constraints: str = Field(default="", description="Optional constraints on the plan.")
    max_steps: int = Field(default=5)


class PlannerOutput(BaseModel):
    response: str = Field(description="Final synthesised response.")
    plan_steps: list[str] = Field(default_factory=list)
    step_outputs: list[str] = Field(default_factory=list)


_PLAN_SYSTEM_PROMPT = """\
You are a planning assistant. Given a goal, produce a step-by-step plan.
Format each step as:
  STEP N: <agent_name> | <task description>

Available agents:
{agent_menu}
  direct | answer this step directly without a specialist

Use "direct" if the step needs no specialist.
End the plan with "DONE" on its own line.
Produce at most {max_steps} steps. Be concise."""

_SYNTHESIS_PROMPT = """\
You are a synthesis assistant. Given a goal and the outputs from each
planning step, produce a final cohesive response that directly addresses
the goal."""


def _parse_plan(text: str) -> list[tuple[str, str]]:
    """Parse STEP N: agent | task lines. Returns list of (agent, task)."""
    steps = []
    for line in text.splitlines():
        m = re.match(r"STEP\s+\d+:\s*(.+?)\s*\|\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            steps.append((m.group(1).strip(), m.group(2).strip()))
    return steps


class PlannerAgent(BaseCoreAgent):
    name = "planner_agent"
    description = (
        "Decomposes a complex multi-step goal into an ordered plan and executes each step "
        "via the right specialist. Use for goals that clearly require 2+ sequential specialist "
        "actions (e.g. 'research X, then write a report', 'read files, analyse, then summarise'). "
        "For single-step tasks call the specialist directly."
    )
    callable_type = CallableType.CORE
    # Exposed to the LLM so it can invoke structured multi-step planning.
    llm_direct_access: bool = True
    input_schema = PlannerInput
    output_schema = PlannerOutput
    policy = CallablePolicy(
        timeout_seconds=600.0,
        requires_approval=False,
        network_allowed=True,
        max_depth_allowed=5,
    )

    async def _execute(self, input: PlannerInput, context: CallContext) -> PlannerOutput:
        if context.model_gateway is None:
            return PlannerOutput(
                response="(model gateway unavailable)",
                plan_steps=[],
            )

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        # Build dynamic agent menu from wired sub_callables
        sub_callables = {c.name: c for c in self.list_sub_callables()}
        menu_lines = [
            f"  {c.name} | {getattr(c, 'description', '').split('.')[0]}"
            for c in sub_callables.values()
            if c.name not in (self.name, "router_agent", "conversation_agent")
        ]
        agent_menu = "\n".join(menu_lines) if menu_lines else "  research_agent | web research"

        # Step 1: generate plan
        plan_system = _PLAN_SYSTEM_PROMPT.format(
            max_steps=input.max_steps,
            agent_menu=agent_menu,
        )
        plan_prompt = f"Goal: {input.goal}"
        if input.constraints:
            plan_prompt += f"\nConstraints: {input.constraints}"

        plan_response = await context.model_gateway.generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=plan_system),
                    ModelMessage(role="user", content=plan_prompt),
                ],
                stream=False,
                temperature=0.3,
            )
        )
        raw_plan = plan_response.content
        steps = _parse_plan(raw_plan)[: input.max_steps]

        if not steps:
            # Fallback: single direct step
            steps = [("direct", input.goal)]

        # Step 2: execute each step (reuse sub_callables dict built for the menu)
        step_labels: list[str] = []
        step_outputs: list[str] = []

        for agent_name, task in steps:
            step_labels.append(f"{agent_name}: {task}")
            if agent_name == "direct":
                step_resp = await context.model_gateway.generate(
                    ModelRequest(
                        messages=[ModelMessage(role="user", content=task)],
                        stream=False,
                        temperature=0.5,
                    )
                )
                step_outputs.append(step_resp.content)
                continue

            specialist = sub_callables.get(agent_name)
            if specialist is None:
                step_outputs.append(f"(specialist {agent_name!r} not available)")
                continue

            child_ctx = context.child(self.name, self.callable_type)
            spec_input = specialist.input_schema.model_validate(
                {"task": task, "query": task, "text": task, "goal": task}
            )
            result = await specialist.invoke(spec_input, child_ctx)
            if result.success and result.output:
                step_outputs.append(result.get_output_field("response", str(result.output)))
            else:
                step_outputs.append(f"(step failed: {result.error})")

        # Step 3: synthesise
        synthesis_parts = [f"Goal: {input.goal}", "Step outputs:"]
        for label, out in zip(step_labels, step_outputs, strict=False):
            synthesis_parts.append(f"  [{label}]\n  {out}")

        final_response = await context.model_gateway.generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=_SYNTHESIS_PROMPT),
                    ModelMessage(role="user", content="\n".join(synthesis_parts)),
                ],
                stream=False,
                temperature=0.5,
            )
        )

        return PlannerOutput(
            response=final_response.content,
            plan_steps=step_labels,
            step_outputs=step_outputs,
        )
