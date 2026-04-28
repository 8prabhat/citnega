from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PlanStepType(StrEnum):
    TOOL = "tool"
    AGENT = "agent"
    WORKFLOW_TEMPLATE_REF = "workflow_template_ref"
    SYNTHESIS = "synthesis"
    APPROVAL_GATE = "approval_gate"


class RetryPolicy(BaseModel):
    max_attempts: int = 1
    backoff_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    jitter: bool = False


class TimeoutPolicy(BaseModel):
    timeout_seconds: float | None = None


class PlanStep(BaseModel):
    step_id: str
    step_type: PlanStepType
    capability_id: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    task: str = ""
    depends_on: list[str] = Field(default_factory=list)
    can_run_in_parallel: bool = False
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    rollback_capability_id: str = ""
    rollback_args: dict[str, Any] = Field(default_factory=dict)
    execution_target: str = "local"
    condition: str = ""
    idempotency_key: str = ""


class WorkflowTemplateStep(BaseModel):
    step_id: str
    capability_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    task: str = ""
    depends_on: list[str] = Field(default_factory=list)
    can_run_in_parallel: bool = False
    execution_target: str = "local"


class WorkflowTemplate(BaseModel):
    name: str
    description: str
    source_path: str = ""
    variables: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[str] = Field(default_factory=lambda: ["plan", "code", "research", "review", "operate"])
    tags: list[str] = Field(default_factory=list)
    max_parallelism: int = 1
    steps: list[WorkflowTemplateStep] = Field(default_factory=list)


class CompiledPlan(BaseModel):
    plan_id: str
    objective: str
    steps: list[PlanStep] = Field(default_factory=list)
    generated_from: str = "manual"
    requires_approval: bool = False
    max_parallelism: int = 1
    execution_policy: dict[str, Any] = Field(default_factory=dict)
    rollback_policy: dict[str, Any] = Field(default_factory=dict)
    stop_conditions: list[str] = Field(default_factory=list)
    synthesis_requirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
