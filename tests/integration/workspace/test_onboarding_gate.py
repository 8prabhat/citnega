"""Integration tests for workspace onboarding enforcement in overlay loading."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from citnega.packages.config.settings import WorkspaceSettings
from citnega.packages.workspace.onboarding import (
    WorkspaceOnboardingError,
    generate_workspace_bundle_manifest,
    write_workspace_bundle_manifest,
)
from citnega.packages.workspace.overlay import load_workspace_overlay


class _MockEnforcer:
    async def enforce(self, *a, **k):
        return None

    async def run_with_timeout(self, _callable_name, coro, *a, **k):
        if asyncio.iscoroutine(coro):
            return await coro
        return coro

    async def check_output_size(self, *a, **k):
        return None


class _MockEmitter:
    def emit(self, *a):
        return None


class _MockTracer:
    def record(self, *a, **k):
        return None


def _write_valid_tool(workfolder: Path, *, name: str = "signed_tool") -> None:
    tools_dir = workfolder / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (workfolder / "agents").mkdir(parents=True, exist_ok=True)
    (workfolder / "workflows").mkdir(parents=True, exist_ok=True)
    (workfolder / "memory").mkdir(parents=True, exist_ok=True)

    (tools_dir / f"{name}.py").write_text(
        """
from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType


class Input(BaseModel):
    text: str = ""


class Output(BaseModel):
    result: str = ""


class SignedTool(BaseCallable):
    name = "signed_tool"
    description = "signed workspace tool"
    callable_type = CallableType.TOOL
    input_schema = Input
    output_schema = Output
    policy = CallablePolicy()

    async def _execute(self, input, context):
        return Output(result="ok")
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_overlay_rejects_untrusted_publisher(tmp_path: Path) -> None:
    _write_valid_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-untrusted",
        publisher="untrusted-inc",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_trusted_publishers=["trusted-inc"],
    )

    with pytest.raises(WorkspaceOnboardingError, match="trusted publisher allowlist"):
        load_workspace_overlay(
            tmp_path,
            enforcer=_MockEnforcer(),
            emitter=_MockEmitter(),
            tracer=_MockTracer(),
            tool_registry={},
            workspace_settings=settings,
        )


def test_overlay_loads_signed_trusted_bundle(tmp_path: Path) -> None:
    _write_valid_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-signed",
        publisher="trusted-inc",
        signature_key="shared-secret",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_require_signature=True,
        onboarding_signature_key="shared-secret",
        onboarding_trusted_publishers=["trusted-inc"],
    )

    loaded = load_workspace_overlay(
        tmp_path,
        enforcer=_MockEnforcer(),
        emitter=_MockEmitter(),
        tracer=_MockTracer(),
        tool_registry={},
        workspace_settings=settings,
    )
    assert "signed_tool" in loaded.tools
