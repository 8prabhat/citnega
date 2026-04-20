"""
MCPBridgeTool — wraps a single MCP tool as a native Citnega IInvocable.

One MCPBridgeTool instance is created per MCP tool discovered on a server.
It follows the exact same BaseCallable pattern as all built-in tools so the
runner/policy layer treats it identically — no special cases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.mcp.client import MCPClient
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer


class _MCPInput(BaseModel):
    """Accepts arbitrary keyword arguments forwarded to the MCP tool."""

    arguments: dict[str, Any] = {}


class MCPBridgeTool(BaseCallable):
    """
    Native Citnega tool backed by an MCP tool on a remote/local server.

    Name follows the pattern: mcp_{server_name}_{tool_name} — unique, readable,
    and avoids collisions with built-in tool names.
    """

    callable_type = CallableType.TOOL
    input_schema = _MCPInput
    output_schema = ToolOutput

    def __init__(
        self,
        enforcer: IPolicyEnforcer,
        emitter: IEventEmitter,
        tracer: ITracer,
        client: MCPClient,
        mcp_tool_name: str,
        mcp_tool_description: str,
        requires_approval: bool = False,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(enforcer, emitter, tracer)
        self._client = client
        self._mcp_tool_name = mcp_tool_name
        # These are normally class attributes but MCPBridgeTool is built
        # dynamically from server-discovered tool descriptors.
        self.name = f"mcp_{client._config.name}_{mcp_tool_name}"
        self.description = f"[MCP:{client._config.name}] {mcp_tool_description}"
        self.policy = tool_policy(
            timeout_seconds=timeout_seconds,
            requires_approval=requires_approval,
            network_allowed=True,
        )

    async def _execute(self, input: _MCPInput, context: CallContext) -> ToolOutput:
        try:
            result = await self._client.call_tool(self._mcp_tool_name, input.arguments)
            return ToolOutput(result=result or f"[{self.name}: empty response]")
        except Exception as exc:
            return ToolOutput(result=f"[{self.name}: {exc}]")
