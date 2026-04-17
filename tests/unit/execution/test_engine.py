from __future__ import annotations

from pydantic import BaseModel
import pytest

from citnega.packages.capabilities import (
    CapabilityDescriptor,
    CapabilityExecutionTraits,
    CapabilityKind,
    CapabilityProvenance,
    CapabilityRecord,
    CapabilityRegistry,
)
from citnega.packages.execution import ExecutionEngine
from citnega.packages.planning import CompiledPlan, PlanStep, PlanStepType, RetryPolicy
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.shared.errors import CallableError


class _TaskInput(BaseModel):
    task: str = ""


class _TaskOutput(BaseModel):
    response: str


class _DummyInvocable(IInvocable):
    callable_type = CallableType.TOOL
    input_schema = _TaskInput
    output_schema = _TaskOutput
    policy = CallablePolicy()

    def __init__(self, name: str, *, fail_times: int = 0) -> None:
        self.name = name
        self.description = name
        self._fail_times = fail_times
        self.calls = 0

    async def invoke(self, input: BaseModel, context: CallContext) -> InvokeResult:
        self.calls += 1
        if self.calls <= self._fail_times:
            return InvokeResult.from_error(
                name=self.name,
                callable_type=self.callable_type,
                error=CallableError(f"{self.name} failed"),
                duration_ms=1,
            )
        return InvokeResult.ok(
            name=self.name,
            callable_type=self.callable_type,
            output=_TaskOutput(response=f"ok:{input.task}"),
            duration_ms=1,
        )

    def get_metadata(self) -> CallableMetadata:
        return CallableMetadata(
            name=self.name,
            description=self.description,
            callable_type=self.callable_type,
            input_schema_json=self.input_schema.model_json_schema(),
            output_schema_json=self.output_schema.model_json_schema(),
            policy=self.policy,
        )


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="exec-tests",
            framework="direct",
            default_model_id="model-x",
        ),
    )


def _registry(*callables: _DummyInvocable) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for callable_obj in callables:
        registry.register(
            CapabilityRecord(
                descriptor=CapabilityDescriptor(
                    capability_id=callable_obj.name,
                    kind=CapabilityKind.TOOL,
                    display_name=callable_obj.name,
                    description=callable_obj.description,
                    execution_traits=CapabilityExecutionTraits(parallel_safe=True),
                    provenance=CapabilityProvenance(source="test"),
                ),
                runtime_object=callable_obj,
            )
        )
    return registry


@pytest.mark.asyncio
async def test_execution_engine_retries_and_rolls_back() -> None:
    prep = _DummyInvocable("prep_tool")
    deploy = _DummyInvocable("deploy_tool", fail_times=5)
    cleanup = _DummyInvocable("cleanup_tool")
    registry = _registry(prep, deploy, cleanup)
    plan = CompiledPlan(
        plan_id="p1",
        objective="deploy",
        max_parallelism=1,
        steps=[
            PlanStep(
                step_id="prep",
                step_type=PlanStepType.TOOL,
                capability_id="prep_tool",
                task="prepare",
                rollback_capability_id="cleanup_tool",
                rollback_args={"task": "cleanup"},
            ),
            PlanStep(
                step_id="deploy",
                step_type=PlanStepType.TOOL,
                capability_id="deploy_tool",
                task="deploy",
                depends_on=["prep"],
                retry_policy=RetryPolicy(max_attempts=2),
            ),
        ],
    )

    result = await ExecutionEngine().execute(
        plan,
        registry,
        _context(),
        fail_fast=True,
        rollback_on_failure=True,
    )

    assert any(item.step_id == "prep" and item.status == "rolled_back" for item in result.step_results)
    assert any(item.step_id == "deploy" and item.status == "failed" and item.attempts == 2 for item in result.step_results)
    assert any("rollback via 'cleanup_tool' succeeded" in action for action in result.rollback_actions)
