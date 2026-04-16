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
  - resolve_file_path() — canonical path normaliser used by file tools AND
    the policy checker so both operate on the same resolved path
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallablePolicy


def resolve_file_path(path_str: str) -> pathlib.Path:
    """
    Normalise a user-supplied file path to a canonical absolute Path.

    Steps:
      1. Expand leading ``~`` to the user home directory.
      2. ``Path.resolve()`` — follows symlinks and collapses ``.`` / ``..``.

    This is the single source of truth shared by file tools (read_file,
    write_file, edit_file, list_dir) and path_check in policy/checks.py, so
    both always operate on the same resolved path.
    """
    expanded = path_str.replace("~", str(pathlib.Path.home()))
    return pathlib.Path(expanded).resolve()


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
