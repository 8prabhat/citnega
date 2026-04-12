"""
Shared base and I/O schema helpers for built-in tools.

All built-in tools:
  - Extend BaseCallable
  - Use CallableType.TOOL
  - Set class-level policy with sane defaults
  - Accept path_resolver injected at construction time

This module provides:
  - ToolOutput — single-field output schema for simple text responses
  - tool_policy() — factory for common policy configurations
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallablePolicy


class ToolOutput(BaseModel):
    """Default single-value output for tools that return text."""

    result: str = Field(default="", description="Tool output text")


def tool_policy(
    *,
    timeout_seconds: float = 30.0,
    requires_approval: bool = False,
    allowed_paths: list[str] | None = None,
    network_allowed: bool = False,
    max_output_bytes: int = 256 * 1024,
    max_depth_allowed: int = 2,
) -> CallablePolicy:
    return CallablePolicy(
        timeout_seconds=timeout_seconds,
        requires_approval=requires_approval,
        allowed_paths=allowed_paths or [],
        network_allowed=network_allowed,
        max_output_bytes=max_output_bytes,
        max_depth_allowed=max_depth_allowed,
    )
