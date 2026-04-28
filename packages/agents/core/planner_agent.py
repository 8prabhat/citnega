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
    preferred_capability: str = Field(
        default="",
        description="Optional preferred tool/agent capability for the first plan step.",
    )


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
        return await self._execute_nextgen(input, context)

    async def _execute_legacy(self, input: PlannerInput, context: CallContext) -> PlannerOutput:
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
            spec_input = specialist.input_schema.model_validate({"task": task})
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

    async def _execute_nextgen(self, input: PlannerInput, context: CallContext) -> PlannerOutput:
        # Delegate genuine multi-step planning to OrchestratorAgent, which already
        # has LLM-driven plan generation and DAG execution with retries + rollback.
        orchestrator = self._get_peer("orchestrator_agent")
        if orchestrator is not None:
            return await self._delegate_to_orchestrator(orchestrator, input, context)

        # Fallback: single-capability compiled plan (unit-test / isolated scenario).
        return await self._execute_single_capability(input, context)

    async def _delegate_to_orchestrator(
        self,
        orchestrator: object,
        input: PlannerInput,
        context: CallContext,
    ) -> PlannerOutput:
        """Hand off multi-step execution to OrchestratorAgent and map its output back."""
        from citnega.packages.agents.core.orchestrator_agent import OrchestratorInput

        orch_input = OrchestratorInput(
            goal=input.goal,
            auto_plan=True,
            max_steps=max(2, input.max_steps),
            rollback_on_failure=True,
            fail_fast=False,
        )
        child_ctx = context.child(self.name, self.callable_type)
        result = await orchestrator.invoke(orch_input, child_ctx)
        if result.success and result.output:
            orch = result.output
            step_outputs = [r.output_excerpt or r.error or r.status for r in orch.step_results]
            return PlannerOutput(
                response=orch.response,
                plan_steps=list(orch.plan),
                step_outputs=step_outputs,
            )
        error_msg = result.error.message if result.error else "Orchestration failed."
        return PlannerOutput(response=error_msg, plan_steps=[])

    async def _execute_single_capability(self, input: PlannerInput, context: CallContext) -> PlannerOutput:
        """Single-capability compiled plan — used when OrchestratorAgent is not wired."""
        from citnega.packages.capabilities import BuiltinCapabilityProvider, CapabilityRegistry
        from citnega.packages.execution import ExecutionEngine
        from citnega.packages.planning import (
            PlanCompiler,
            PlanValidator,
        )
        from citnega.packages.protocol.events.planning import PlanCompiledEvent, PlanValidatedEvent
        from citnega.packages.strategy import StrategySpec

        runtime_callables = self._discover_runtime_callables()
        if not runtime_callables:
            return PlannerOutput(response="(no capabilities available for planning)", plan_steps=[])

        selected_capability = self._select_capability(input, runtime_callables)
        if selected_capability is None:
            return PlannerOutput(response="(unable to choose a capability for this goal)", plan_steps=[])

        registry = CapabilityRegistry()
        records, diagnostics = BuiltinCapabilityProvider().load(runtime_callables)
        if diagnostics.has_required_failures:
            return PlannerOutput(response="(planner capability registry bootstrap failed)", plan_steps=[])
        registry.register_many(records, overwrite=True)

        strategy = StrategySpec(
            mode="plan",
            objective=input.goal,
            parallelism_budget=max(1, min(input.max_steps, 4)),
            success_criteria=["Complete the objective with deterministic execution."],
        )
        compiled_plan = PlanCompiler().compile_goal(
            input.goal,
            strategy=strategy,
            capability_id=selected_capability,
            args={
                "task": input.goal,
                "goal": input.goal,
                "query": input.goal,
                "text": input.goal,
                "user_input": input.goal,
            },
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
            return PlannerOutput(
                response="Plan validation failed: " + "; ".join(validation.errors),
                plan_steps=[],
            )

        engine = ExecutionEngine(event_emitter=self._event_emitter)
        execution_result = await engine.execute(
            compiled_plan,
            registry,
            context.child(self.name, self.callable_type),
            fail_fast=True,
            rollback_on_failure=True,
        )
        plan_steps = [f"{step.step_id}: {step.capability_id}" for step in compiled_plan.steps]
        step_outputs = [
            item.output_excerpt or item.error or item.status
            for item in execution_result.step_results
        ]
        response = self._build_execution_response(execution_result.step_results)
        if not response:
            response = execution_result.response
        return PlannerOutput(response=response, plan_steps=plan_steps, step_outputs=step_outputs)

    def _get_peer(self, name: str) -> object | None:
        for c in self.list_sub_callables():
            if c.name == name:
                return c
        return None

    def _discover_runtime_callables(self) -> dict[str, object]:
        callables: dict[str, object] = {}
        for name, obj in self._tool_registry.items():
            callables[name] = obj
        for peer in self.list_sub_callables():
            if peer.name in {self.name, "router_agent", "conversation_agent"}:
                continue
            callables[peer.name] = peer
        return callables

    def _select_capability(
        self,
        input: PlannerInput,
        callables: dict[str, object],
    ) -> str | None:
        preferred = input.preferred_capability.strip()
        if preferred and preferred in callables:
            return preferred

        text = input.goal.lower()
        if "test" in text or "quality" in text:
            for candidate in ("qa_agent", "quality_gate", "test_matrix"):
                if candidate in callables:
                    return candidate
        if "code" in text or "refactor" in text or "debug" in text:
            for candidate in ("code_agent", "repo_map"):
                if candidate in callables:
                    return candidate
        if "research" in text or "find" in text or "latest" in text:
            for candidate in ("research_agent", "search_web"):
                if candidate in callables:
                    return candidate

        for name in sorted(callables):
            return name
        return None

    @staticmethod
    def _build_execution_response(step_results) -> str:
        for item in step_results:
            if item.status == "completed" and item.output_excerpt:
                return item.output_excerpt
        return ""

    @staticmethod
    def _nextgen_planning_enabled() -> bool:
        try:
            from citnega.packages.config.loaders import load_settings

            return load_settings().nextgen.planning_enabled
        except Exception:
            return False
