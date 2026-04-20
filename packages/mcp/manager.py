"""
MCPManager — lifecycle manager for all configured MCP servers.

Connects to each enabled MCP server on start(), discovers their tools,
wraps them as MCPBridgeTool instances, and exposes them via get_bridge_tools()
so the runner can add them to its callable registry.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.config.settings import MCPSettings
    from citnega.packages.mcp.bridge import MCPBridgeTool
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer


class MCPManager:
    """Manages the lifecycle of MCP server connections and bridge tools."""

    def __init__(
        self,
        settings: MCPSettings,
        enforcer: IPolicyEnforcer,
        emitter: IEventEmitter,
        tracer: ITracer,
    ) -> None:
        self._settings = settings
        self._deps = (enforcer, emitter, tracer)
        self._clients: dict[str, object] = {}  # name → MCPClient
        self._bridge_tools: dict[str, MCPBridgeTool] = {}

    async def start(self) -> None:
        """Connect to all enabled MCP servers and discover their tools."""
        if not self._settings.enabled:
            return

        from citnega.packages.mcp.bridge import MCPBridgeTool
        from citnega.packages.mcp.client import MCPClient

        for cfg in self._settings.servers:
            if not cfg.enabled:
                continue
            try:
                client = MCPClient(cfg)
                await client.connect()
                self._clients[cfg.name] = client

                tools = await client.list_tools()
                for tool_desc in tools:
                    bridge = MCPBridgeTool(
                        *self._deps,
                        client=client,
                        mcp_tool_name=tool_desc["name"],
                        mcp_tool_description=tool_desc.get("description", ""),
                        requires_approval=cfg.requires_approval,
                        timeout_seconds=cfg.timeout_seconds,
                    )
                    self._bridge_tools[bridge.name] = bridge
            except Exception as exc:
                # Non-fatal: log and continue with other servers
                from citnega.packages.observability.logging_setup import runtime_logger
                runtime_logger.warning(
                    "mcp_server_connect_failed",
                    server=cfg.name,
                    error=str(exc),
                )

    async def stop(self) -> None:
        """Gracefully disconnect from all connected MCP servers."""
        for name, client in list(self._clients.items()):
            with contextlib.suppress(Exception):
                await client.disconnect()  # type: ignore[attr-defined]
        self._clients.clear()
        self._bridge_tools.clear()

    def get_bridge_tools(self) -> dict[str, MCPBridgeTool]:
        """Return all bridge tools discovered from connected MCP servers."""
        return dict(self._bridge_tools)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients.keys())
