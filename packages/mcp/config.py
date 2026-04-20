"""
MCP server configuration types.

MCPServerConfig is the single source of truth for all fields needed to
connect to and use an MCP server. MCPTransport enumerates the supported
transport layers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MCPTransport(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerConfig(BaseModel):
    """Full configuration for a single MCP server connection."""

    name: str = Field(description="Unique name for this MCP server instance.")
    transport: MCPTransport = Field(
        default=MCPTransport.STDIO,
        description="Transport protocol to use when connecting to the server.",
    )
    # stdio transport
    command: list[str] = Field(
        default_factory=list,
        description="Command + arguments to launch the server process (stdio only).",
    )
    # sse / streamable_http transport
    url: str = Field(
        default="",
        description="Server URL for sse or streamable_http transport.",
    )
    # Process environment
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables injected into the server process.",
    )
    enabled: bool = Field(default=True)
    timeout_seconds: float = Field(
        default=30.0,
        description="Per-call timeout in seconds for MCP tool invocations.",
    )
    requires_approval: bool = Field(
        default=False,
        description="When True, tool calls to this server need user approval via PolicyEnforcer.",
    )
    description: str = Field(default="", description="Human-readable description shown in the F2 UI.")
    tags: list[str] = Field(default_factory=list, description="Categorisation tags for filtering.")
