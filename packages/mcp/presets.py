"""
Well-known MCP server presets.

Each preset is an MCPServerConfig with sensible defaults. Env vars with
empty-string defaults are placeholders — the user fills them in via F2 settings
before enabling the server.
"""

from __future__ import annotations

from citnega.packages.mcp.config import MCPServerConfig, MCPTransport

PRESETS: dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="filesystem",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/"],
        description="Read and write files via MCP filesystem server.",
        tags=["filesystem"],
    ),
    "github": MCPServerConfig(
        name="github",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": ""},
        description="GitHub repositories, issues, and pull requests.",
        tags=["github", "vcs"],
        requires_approval=True,
    ),
    "postgres": MCPServerConfig(
        name="postgres",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-postgres"],
        env={"POSTGRES_CONNECTION_STRING": ""},
        description="PostgreSQL database read/write access.",
        tags=["database"],
        requires_approval=True,
    ),
    "brave_search": MCPServerConfig(
        name="brave_search",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": ""},
        description="Brave Search web results.",
        tags=["web", "search"],
    ),
    "puppeteer": MCPServerConfig(
        name="puppeteer",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-puppeteer"],
        description="Headless browser automation via Puppeteer.",
        tags=["browser"],
        requires_approval=True,
    ),
    "slack": MCPServerConfig(
        name="slack",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-slack"],
        env={"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        description="Slack workspace messaging and channel access.",
        tags=["messaging"],
        requires_approval=True,
    ),
    "memory": MCPServerConfig(
        name="memory",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-memory"],
        description="Persistent key-value memory store across sessions.",
        tags=["memory"],
    ),
    "sqlite": MCPServerConfig(
        name="sqlite",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-sqlite", "--db-path", ""],
        description="SQLite database read/write access.",
        tags=["database"],
    ),
    "everything": MCPServerConfig(
        name="everything",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-everything"],
        description="MCP reference server for testing and development.",
        tags=["dev", "test"],
    ),
    "sequential_thinking": MCPServerConfig(
        name="sequential_thinking",
        transport=MCPTransport.STDIO,
        command=["npx", "-y", "@modelcontextprotocol/server-sequential-thinking"],
        description="Structured sequential reasoning for complex problems.",
        tags=["reasoning"],
    ),
    "fetch": MCPServerConfig(
        name="fetch",
        transport=MCPTransport.STDIO,
        command=["uvx", "mcp-server-fetch"],
        description="HTTP fetch with automatic Markdown conversion.",
        tags=["web"],
    ),
    "git": MCPServerConfig(
        name="git",
        transport=MCPTransport.STDIO,
        command=["uvx", "mcp-server-git", "--repository", "."],
        description="Git operations on the local repository.",
        tags=["vcs"],
    ),
}
