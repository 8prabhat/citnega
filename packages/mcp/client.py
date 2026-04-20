"""
MCPClient — thin async wrapper around mcp.ClientSession for one server.

All MCP SDK imports are lazy (inside methods) so the package loads cleanly
without the optional 'mcp[cli]' dependency installed.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.mcp.config import MCPServerConfig


class MCPClient:
    """Manages the lifecycle of a connection to a single MCP server."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._session: Any = None
        self._exit_stack: Any = None

    async def connect(self) -> None:
        """Connect to the MCP server. Raises RuntimeError if SDK not installed."""
        from citnega.packages.mcp.config import MCPTransport

        try:
            from mcp import ClientSession  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "MCP SDK not installed: pip install 'mcp[cli]'"
            ) from exc

        import contextlib as _cl
        self._exit_stack = _cl.AsyncExitStack()
        await self._exit_stack.__aenter__()

        if self._config.transport == MCPTransport.STDIO:
            from mcp import StdioServerParameters  # type: ignore[import]
            from mcp.client.stdio import stdio_client  # type: ignore[import]

            if not self._config.command:
                raise ValueError(f"MCP server '{self._config.name}': command is required for stdio transport")

            merged_env = {**os.environ, **self._config.env}
            params = StdioServerParameters(
                command=self._config.command[0],
                args=self._config.command[1:],
                env=merged_env,
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))

        elif self._config.transport in (MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP):
            if not self._config.url:
                raise ValueError(
                    f"MCP server '{self._config.name}': url is required for {self._config.transport} transport"
                )
            try:
                from mcp.client.sse import sse_client  # type: ignore[import]
            except ImportError:
                from mcp.client.streamable_http import streamablehttp_client as sse_client  # type: ignore[import]

            read, write = await self._exit_stack.enter_async_context(sse_client(self._config.url))
        else:
            raise ValueError(f"Unsupported MCP transport: {self._config.transport}")

        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return list of tools provided by this server."""
        if self._session is None:
            raise RuntimeError(f"MCP client '{self._config.name}' not connected — call connect() first")
        result = await self._session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
            }
            for t in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the server and return its text output."""
        if self._session is None:
            raise RuntimeError(f"MCP client '{self._config.name}' not connected")
        result = await self._session.call_tool(name, arguments)
        return "\n".join(
            c.text
            for c in result.content
            if hasattr(c, "text") and c.text
        )

    async def disconnect(self) -> None:
        """Gracefully disconnect from the server."""
        if self._exit_stack is not None:
            with contextlib.suppress(Exception):
                await self._exit_stack.__aexit__(None, None, None)
        self._session = None
        self._exit_stack = None
