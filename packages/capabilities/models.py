from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallablePolicy


class CapabilityKind(StrEnum):
    TOOL = "tool"
    AGENT = "agent"
    WORKFLOW_TEMPLATE = "workflow_template"
    SKILL = "skill"


class SideEffectLevel(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"


class CapabilityExecutionTraits(BaseModel):
    parallel_safe: bool = False
    side_effect_level: SideEffectLevel = SideEffectLevel.NONE
    resource_scope: str = "global"
    requires_exclusive_workspace: bool = False
    supports_remote_execution: bool = False


class CapabilityProvenance(BaseModel):
    source: str
    path: str = ""
    publisher: str = ""
    version: str = ""
    stability_level: str = "stable"


class CapabilityDescriptor(BaseModel):
    capability_id: str
    kind: CapabilityKind
    display_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    policy: CallablePolicy | None = None
    execution_traits: CapabilityExecutionTraits = Field(default_factory=CapabilityExecutionTraits)
    supported_modes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    language_profiles: list[str] = Field(default_factory=list)
    provenance: CapabilityProvenance


@dataclass(slots=True)
class CapabilityRecord:
    descriptor: CapabilityDescriptor
    runtime_object: object | None = None
