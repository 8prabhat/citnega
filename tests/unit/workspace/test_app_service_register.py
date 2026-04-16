"""Unit tests for ApplicationService.register_callable, hot_reload_workfolder, save_workspace_path"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from citnega.packages.runtime.app_service import ApplicationService
from citnega.packages.shared.registry import BaseRegistry, CallableRegistry
from citnega.packages.workspace.loader import DynamicLoader
from citnega.packages.workspace.templates import FallbackTemplates, ScaffoldSpec
from citnega.packages.workspace.writer import WorkspaceWriter

if TYPE_CHECKING:
    from pathlib import Path

# ── Stubs ──────────────────────────────────────────────────────────────────────


class _MockRuntime:
    def __init__(self):
        self._registry = BaseRegistry("test")

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


class _MockEnforcer:
    async def enforce(self, *a, **k):
        pass

    async def run_with_timeout(self, c, coro, *a, **k):
        if asyncio.iscoroutine(coro):
            return asyncio.get_event_loop().run_until_complete(coro)
        return coro

    async def check_output_size(self, *a, **k):
        pass


class _MockEmitter:
    def emit(self, *a):
        pass

    def get_queue(self, *a):
        pass

    def close_queue(self, *a):
        pass


class _MockApprovalMgr:
    pass


def _make_service(tmp_path: Path | None = None) -> ApplicationService:
    runtime = _MockRuntime()
    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = runtime
    svc._emitter = _MockEmitter()
    svc._approval_manager = _MockApprovalMgr()
    svc._model_gateway = None
    svc._kb_store = None
    svc._callable_registry = CallableRegistry()
    svc._enforcer = _MockEnforcer()
    svc._tracer = MagicMock()
    svc._app_home = tmp_path
    return svc


def _make_callable(name: str, kind: str, class_name: str, tmp_path: Path):
    """Write a tool to tmp_path and load it, returning the instance."""
    spec = ScaffoldSpec(kind=kind, class_name=class_name, name=name, description="test")
    source = (
        FallbackTemplates.render_tool(spec)
        if kind == "tool"
        else FallbackTemplates.render_agent(spec)
    )
    p = tmp_path / f"{name}.py"
    p.write_text(source, encoding="utf-8")

    loader = DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())
    loaded = loader.load_directory(tmp_path)
    return loaded[name]


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestRegisterCallable:
    def test_tool_appears_in_tool_registry(self, tmp_path: Path) -> None:
        svc = _make_service()
        obj = _make_callable("alpha_tool", "tool", "AlphaTool", tmp_path)
        svc.register_callable(obj)
        assert "alpha_tool" in svc._callable_registry.get_tools()

    def test_tool_appears_in_runtime_registry(self, tmp_path: Path) -> None:
        svc = _make_service()
        obj = _make_callable("beta_tool", "tool", "BetaTool", tmp_path)
        svc.register_callable(obj)
        assert "beta_tool" in svc._runtime.callable_registry

    def test_agent_goes_to_agent_registry(self, tmp_path: Path) -> None:
        svc = _make_service()
        spec = ScaffoldSpec(kind="agent", class_name="MyAgent", name="my_agent", description="test")
        source = FallbackTemplates.render_agent(spec)
        (tmp_path / "my_agent.py").write_text(source)
        loader = DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())
        loaded = loader.load_directory(tmp_path)
        if "my_agent" in loaded:
            svc.register_callable(loaded["my_agent"])
            assert "my_agent" in svc._callable_registry.get_agents()

    def test_overwrite_does_not_raise(self, tmp_path: Path) -> None:
        svc = _make_service()
        obj = _make_callable("gamma_tool", "tool", "GammaTool", tmp_path)
        svc.register_callable(obj)
        svc.register_callable(obj)  # second time must not raise

    def test_nameless_callable_raises(self) -> None:
        svc = _make_service()
        nameless = MagicMock()
        nameless.name = ""
        with pytest.raises(ValueError, match="'name' attribute"):
            svc.register_callable(nameless)

    def test_invalid_contract_callable_raises(self) -> None:
        from citnega.packages.protocol.callables.types import CallableType

        svc = _make_service()
        invalid = MagicMock()
        invalid.name = "invalid_tool"
        invalid.description = "invalid"
        invalid.callable_type = CallableType.TOOL
        invalid.input_schema = object  # not a BaseModel subclass
        invalid.output_schema = object
        invalid.policy = object()
        invalid._execute = MagicMock()

        with pytest.raises(ValueError, match="input_schema"):
            svc.register_callable(invalid)

    def test_list_tools_shows_registered(self, tmp_path: Path) -> None:
        svc = _make_service()
        obj = _make_callable("list_test_tool", "tool", "ListTestTool", tmp_path)
        svc.register_callable(obj)
        names = [m.name for m in svc.list_tools()]
        assert "list_test_tool" in names


class TestHotReloadWorkfolder:
    def test_loads_and_registers_tools(self, tmp_path: Path) -> None:
        svc = _make_service()
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()

        spec = ScaffoldSpec(kind="tool", class_name="HotTool", name="hot_tool", description="test")
        source = FallbackTemplates.render_tool(spec)
        w.write_tool("HotTool", source)

        loader = DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())
        result = asyncio.run(svc.hot_reload_workfolder(tmp_path, loader))

        assert "hot_tool" in result["registered"]
        assert result["errors"] == []
        assert "hot_tool" in svc._callable_registry.get_tools()

    def test_empty_workfolder_returns_empty(self, tmp_path: Path) -> None:
        svc = _make_service()
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        loader = DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())
        result = asyncio.run(svc.hot_reload_workfolder(tmp_path, loader))
        assert result["registered"] == []
        assert result["errors"] == []

    def test_hot_reload_rejects_missing_required_manifest(self, tmp_path: Path) -> None:
        app_home = tmp_path / "app_home"
        config_dir = app_home / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "settings.toml").write_text(
            "[workspace]\nonboarding_require_manifest = true\n",
            encoding="utf-8",
        )

        workfolder = tmp_path / "workfolder"
        writer = WorkspaceWriter(workfolder)
        writer.ensure_dirs()

        svc = _make_service(tmp_path=app_home)
        loader = DynamicLoader(_MockEnforcer(), _MockEmitter(), MagicMock())

        with pytest.raises(ValueError, match="manifest is required but missing"):
            asyncio.run(svc.hot_reload_workfolder(workfolder, loader))


class TestSaveWorkspacePath:
    def test_creates_workspace_toml(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir()
        svc = _make_service(tmp_path=tmp_path)
        svc.save_workspace_path("/my/workspace")
        toml = tmp_path / "config" / "workspace.toml"
        assert toml.exists()
        assert "/my/workspace" in toml.read_text()

    def test_no_app_home_is_noop(self) -> None:
        svc = _make_service(tmp_path=None)
        svc.save_workspace_path("/any/path")  # must not raise
