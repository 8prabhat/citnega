"""
Integration test: full pipeline from ScaffoldGenerator → CodeValidator → WorkspaceWriter
→ DynamicLoader → ApplicationService.register_callable → list_tools/list_agents.

Uses tmp_path (no real database, no live model server).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.runtime.app_service import ApplicationService
from citnega.packages.shared.registry import BaseRegistry, CallableRegistry
from citnega.packages.workspace.loader import DynamicLoader
from citnega.packages.workspace.scaffold import ScaffoldGenerator
from citnega.packages.workspace.templates import ScaffoldSpec
from citnega.packages.workspace.validator import CodeValidator
from citnega.packages.workspace.writer import WorkspaceWriter

if TYPE_CHECKING:
    from pathlib import Path

# ── Shared stubs ──────────────────────────────────────────────────────────────


class _MockEnforcer:
    async def enforce(self, *a, **k):
        pass

    async def run_with_timeout(self, c, coro, *a, **k):
        if asyncio.iscoroutine(coro):
            return await coro
        return coro

    async def check_output_size(self, *a, **k):
        pass


class _MockEmitter:
    def emit(self, *a):
        pass


class _MockTracer:
    def record(self, *a, **k):
        pass


class _MockRuntime:
    def __init__(self):
        self._registry = BaseRegistry("integration-test")

    @property
    def callable_registry(self):
        return self._registry

    @property
    def adapter(self):
        return MagicMock()

    def get_runner(self, session_id: str):
        return None

    async def refresh_runners(self):
        return {"refreshed": [], "skipped": []}


def _make_service() -> ApplicationService:
    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = _MockRuntime()
    svc._emitter = _MockEmitter()
    svc._approval_manager = MagicMock()
    svc._model_gateway = None
    svc._kb_store = None
    svc._callable_registry = CallableRegistry()
    svc._enforcer = _MockEnforcer()
    svc._tracer = _MockTracer()
    svc._app_home = None
    return svc


def _make_loader(tool_registry: dict | None = None) -> DynamicLoader:
    return DynamicLoader(
        enforcer=_MockEnforcer(),
        emitter=_MockEmitter(),
        tracer=_MockTracer(),
        tool_registry=tool_registry or {},
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestCreateAndRegisterTool:
    """Full pipeline for a tool."""

    def test_tool_pipeline(self, tmp_path: Path) -> None:
        spec = ScaffoldSpec(
            kind="tool",
            class_name="IntegrationTool",
            name="integration_tool",
            description="Integration test tool",
            parameters=[{"name": "query", "type": "str", "description": "The query"}],
        )

        # Generate
        source = asyncio.run(ScaffoldGenerator(model_gateway=None).generate(spec))

        # Validate
        result = CodeValidator().validate(source, spec.class_name, spec.kind)
        assert result.ok, f"Validation failed: {result.errors}"

        # Write
        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()
        written = writer.write_tool(spec.class_name, source)
        assert written.exists()

        # Load
        loader = _make_loader()
        loaded = loader.load_directory(tmp_path / "tools")
        assert spec.name in loaded

        # Register
        svc = _make_service()
        svc.register_callable(loaded[spec.name])

        # Verify visible in list_tools
        tool_names = [m.name for m in svc.list_tools()]
        assert spec.name in tool_names

    def test_tool_callable_type_is_tool(self, tmp_path: Path) -> None:
        spec = ScaffoldSpec(
            kind="tool", class_name="TypeCheckTool", name="type_check_tool", description="type test"
        )
        source = asyncio.run(ScaffoldGenerator(None).generate(spec))
        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()
        writer.write_tool(spec.class_name, source)

        loader = _make_loader()
        loaded = loader.load_directory(tmp_path / "tools")
        assert loaded[spec.name].callable_type == CallableType.TOOL


class TestCreateAndRegisterAgent:
    """Full pipeline for a specialist agent."""

    def test_agent_pipeline(self, tmp_path: Path) -> None:
        spec = ScaffoldSpec(
            kind="agent",
            class_name="IntegrationAgent",
            name="integration_agent",
            description="Integration test agent",
            system_prompt="You are a test agent.",
            tool_whitelist=["integration_tool"],
        )

        source = asyncio.run(ScaffoldGenerator(None).generate(spec))
        result = CodeValidator().validate(source, spec.class_name, spec.kind)
        assert result.ok, f"Validation failed: {result.errors}"

        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()
        writer.write_agent(spec.class_name, source)

        loader = _make_loader()
        loaded = loader.load_directory(tmp_path / "agents")
        assert spec.name in loaded

        svc = _make_service()
        svc.register_callable(loaded[spec.name])

        agent_names = [m.name for m in svc.list_agents()]
        assert spec.name in agent_names


class TestHotReloadIntegration:
    """hot_reload_workfolder end-to-end."""

    def test_hot_reload_registers_all_kinds(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()

        for kind, cls_name, name in [
            ("tool", "HotTool", "hot_tool"),
            ("agent", "HotAgent", "hot_agent"),
            ("workflow", "HotWorkflow", "hot_workflow"),
        ]:
            spec = ScaffoldSpec(kind=kind, class_name=cls_name, name=name, description="hot test")
            source = asyncio.run(ScaffoldGenerator(None).generate(spec))
            if kind == "tool":
                writer.write_tool(cls_name, source)
            elif kind == "agent":
                writer.write_agent(cls_name, source)
            else:
                writer.write_workflow(cls_name, source)

        svc = _make_service()
        loader = _make_loader()
        # Disable nextgen workflows so Python workflow files are loaded directly.
        with patch(
            "citnega.packages.workspace.onboarding.enforce_workspace_onboarding"
        ), patch(
            "citnega.packages.config.loaders.load_settings"
        ) as mock_settings:
            from citnega.packages.config.loaders import load_settings as _real_load
            real_settings = _real_load()
            real_settings.nextgen.workflows_enabled = False
            mock_settings.return_value = real_settings
            result = asyncio.run(svc.hot_reload_workfolder(tmp_path, loader))

        assert "hot_tool" in result["registered"]
        assert "hot_agent" in result["registered"]
        assert "hot_workflow" in result["registered"]
        assert result["errors"] == []

    def test_hot_reload_idempotent(self, tmp_path: Path) -> None:
        """Running /refresh twice must not raise."""
        writer = WorkspaceWriter(tmp_path)
        writer.ensure_dirs()

        spec = ScaffoldSpec(
            kind="tool", class_name="IdempTool", name="idemp_tool", description="test"
        )
        writer.write_tool(spec.class_name, asyncio.run(ScaffoldGenerator(None).generate(spec)))

        svc = _make_service()
        loader = _make_loader()
        asyncio.run(svc.hot_reload_workfolder(tmp_path, loader))
        result2 = asyncio.run(svc.hot_reload_workfolder(tmp_path, loader))
        assert result2["errors"] == []
