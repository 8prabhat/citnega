from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionBatch(BaseModel):
    batch_id: str
    step_ids: list[str] = Field(default_factory=list)


class ExecutionStepResult(BaseModel):
    step_id: str
    capability_id: str
    status: str
    attempts: int
    dependency_ids: list[str] = Field(default_factory=list)
    output_excerpt: str = ""
    error: str = ""
    duration_ms: int = 0
    execution_target: str = "local"


class ExecutionResult(BaseModel):
    response: str = ""
    batches: list[ExecutionBatch] = Field(default_factory=list)
    step_results: list[ExecutionStepResult] = Field(default_factory=list)
    rollback_actions: list[str] = Field(default_factory=list)
