"""Integration tests: MCP config, presets, and manager lifecycle."""
from __future__ import annotations

import pytest


def test_mcp_server_config_validates_transport() -> None:
    from citnega.packages.mcp.config import MCPServerConfig, MCPTransport

    cfg = MCPServerConfig(name="test", transport=MCPTransport.STDIO, command=["echo"])
    assert cfg.transport == MCPTransport.STDIO
    assert cfg.name == "test"


def test_mcp_server_config_defaults() -> None:
    from citnega.packages.mcp.config import MCPServerConfig

    cfg = MCPServerConfig(name="minimal")
    assert cfg.enabled is True
    assert cfg.timeout_seconds == 30.0
    assert cfg.requires_approval is False


def test_preset_names_are_unique() -> None:
    from citnega.packages.mcp.presets import PRESETS

    names = list(PRESETS.keys())
    assert len(names) == len(set(names))


def test_preset_names_match_config_names() -> None:
    from citnega.packages.mcp.presets import PRESETS

    for key, cfg in PRESETS.items():
        assert cfg.name == key, f"Preset key {key!r} doesn't match cfg.name {cfg.name!r}"


def test_all_presets_have_commands_or_urls() -> None:
    from citnega.packages.mcp.config import MCPTransport
    from citnega.packages.mcp.presets import PRESETS

    for name, cfg in PRESETS.items():
        if cfg.transport == MCPTransport.STDIO:
            assert len(cfg.command) > 0, f"Preset {name} has no command"
        else:
            assert cfg.url, f"Preset {name} has no URL"


@pytest.mark.asyncio
async def test_manager_skips_disabled_servers() -> None:
    from unittest.mock import MagicMock
    from citnega.packages.config.settings import MCPServerConfig, MCPSettings
    from citnega.packages.mcp.manager import MCPManager

    settings = MCPSettings(
        enabled=True,
        servers=[MCPServerConfig(name="disabled_server", enabled=False, command=["npx", "whatever"])],
    )
    mgr = MCPManager(
        settings=settings,
        enforcer=MagicMock(),
        emitter=MagicMock(),
        tracer=MagicMock(),
    )
    await mgr.start()
    assert len(mgr.get_bridge_tools()) == 0
    await mgr.stop()


@pytest.mark.asyncio
async def test_manager_no_start_when_mcp_disabled() -> None:
    from unittest.mock import MagicMock
    from citnega.packages.config.settings import MCPSettings
    from citnega.packages.mcp.manager import MCPManager

    settings = MCPSettings(enabled=False)
    mgr = MCPManager(
        settings=settings,
        enforcer=MagicMock(),
        emitter=MagicMock(),
        tracer=MagicMock(),
    )
    await mgr.start()
    assert len(mgr.get_bridge_tools()) == 0
    await mgr.stop()
