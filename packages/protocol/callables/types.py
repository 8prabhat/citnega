"""Callable type definitions: enums, policy, metadata."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CallableType(StrEnum):
    TOOL = "tool"
    SPECIALIST = "specialist"
    CORE = "core"


class CallablePolicy(BaseModel):
    """Execution constraints applied by PolicyEnforcer before any callable runs."""

    timeout_seconds: float = 30.0
    requires_approval: bool = False
    allowed_paths: list[str] = Field(default_factory=list)  # empty = no file access
    network_allowed: bool = False
    max_output_bytes: int = 256 * 1024  # 256 KB default
    max_depth_allowed: int = 2


class CallableMetadata(BaseModel):
    """Static description of a callable — used for routing and introspection."""

    name: str
    description: str
    callable_type: CallableType
    input_schema_json: dict[str, object]  # JSON schema of input_schema
    output_schema_json: dict[str, object]  # JSON schema of output_schema
    policy: CallablePolicy
