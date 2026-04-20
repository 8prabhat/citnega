from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MentalModelClauseType(StrEnum):
    ORDERING = "ordering"
    RISK = "risk"
    VALIDATION = "validation"
    APPROVAL = "approval"
    PARALLELISM = "parallelism"
    GENERAL = "general"


class MentalModelClause(BaseModel):
    clause_type: MentalModelClauseType
    text: str


class MentalModelSpec(BaseModel):
    source_text: str = ""
    clauses: list[MentalModelClause] = Field(default_factory=list)
    negations: list[str] = Field(
        default_factory=list,
        description="Explicit prohibitions extracted by LLM compiler (do-not instructions).",
    )
    recommended_parallelism: int = 1
    risk_posture: str = "balanced"


class SkillDescriptor(BaseModel):
    name: str
    description: str
    content_path: str
    triggers: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    supported_modes: list[str] = Field(default_factory=lambda: ["chat", "plan", "explore", "research", "code", "review", "operate"])
    tags: list[str] = Field(default_factory=list)
    body: str = ""


class StrategySpec(BaseModel):
    mode: str = "chat"
    objective: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    risk_posture: str = "balanced"
    planning_depth: str = "standard"
    parallelism_budget: int = 1
    preferred_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    approval_policy: str = "default"
    evidence_requirements: list[str] = Field(default_factory=list)
    user_style_constraints: list[str] = Field(default_factory=list)
    active_skills: list[str] = Field(default_factory=list)
    mental_model_clauses: list[MentalModelClause] = Field(default_factory=list)
