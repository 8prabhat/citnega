from __future__ import annotations

from pydantic import Field

from citnega.packages.protocol.events.base import BaseEvent


class PlanCompiledEvent(BaseEvent):
    event_type: str = "PlanCompiledEvent"
    plan_id: str
    objective: str
    generated_from: str
    step_count: int


class PlanValidatedEvent(BaseEvent):
    event_type: str = "PlanValidatedEvent"
    plan_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)


class SkillActivatedEvent(BaseEvent):
    event_type: str = "SkillActivatedEvent"
    skill_name: str
    rationale: str = ""


class MentalModelCompiledEvent(BaseEvent):
    event_type: str = "MentalModelCompiledEvent"
    clause_count: int
    risk_posture: str
    recommended_parallelism: int


class WorkflowTemplateExpandedEvent(BaseEvent):
    event_type: str = "WorkflowTemplateExpandedEvent"
    workflow_name: str
    plan_id: str
    step_count: int


class ExecutionBatchStartedEvent(BaseEvent):
    event_type: str = "ExecutionBatchStartedEvent"
    plan_id: str
    batch_id: str
    step_ids: list[str] = Field(default_factory=list)


class ExecutionBatchCompletedEvent(BaseEvent):
    event_type: str = "ExecutionBatchCompletedEvent"
    plan_id: str
    batch_id: str
    step_ids: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


class CapabilityLoadFailedEvent(BaseEvent):
    event_type: str = "CapabilityLoadFailedEvent"
    capability_id: str
    source: str
    path: str
    error: str
    required: bool = False


class ParallelExecutionConflictEvent(BaseEvent):
    event_type: str = "ParallelExecutionConflictEvent"
    plan_id: str
    step_id: str
    conflicting_step_id: str
    reason: str
