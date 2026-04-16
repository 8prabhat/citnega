"""Unit tests for P2 tooling additions (artifact_pack)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.tools.builtin.artifact_pack import ArtifactPackInput, ArtifactPackTool


class _StubPathResolver:
    def __init__(self, root: Path) -> None:
        self.artifacts_dir = root / "artifacts"
        self._events_dir = root / "events"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._events_dir.mkdir(parents=True, exist_ok=True)

    def event_log_path(self, run_id: str) -> Path:
        return self._events_dir / f"{run_id}.jsonl"


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="tests",
            framework="direct",
            default_model_id="x",
        ),
    )


def _make_tool(path_resolver: _StubPathResolver) -> ArtifactPackTool:
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return ArtifactPackTool(
        policy_enforcer=enforcer,
        event_emitter=emitter,
        tracer=tracer,
        path_resolver=path_resolver,
    )


@pytest.mark.asyncio
async def test_artifact_pack_creates_manifest_summary_and_zip(tmp_path: Path) -> None:
    resolver = _StubPathResolver(tmp_path)
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    tracked = working_dir / "notes.txt"
    tracked.write_text("release payload\n", encoding="utf-8")

    event_log = resolver.event_log_path("r1")
    event_log.write_text('{"event_type":"RunStateEvent","state":"completed"}\n', encoding="utf-8")

    tool = _make_tool(resolver)
    result = await tool.invoke(
        ArtifactPackInput(
            working_dir=str(working_dir),
            run_id="r1",
            pack_name="release-candidate",
            include_git=False,
            include_event_log=True,
            include_paths=[str(tracked)],
            metadata={"owner": "qa"},
            notes="integration handoff",
            create_zip=True,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert Path(out.manifest_path).exists()
    assert Path(out.summary_path).exists()
    assert out.bundle_path and Path(out.bundle_path).exists()
    assert any(path.startswith("inputs/") for path in out.included_files)

    manifest = json.loads(Path(out.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifact_id"] == out.artifact_id
    assert manifest["metadata"]["owner"] == "qa"


@pytest.mark.asyncio
async def test_artifact_pack_non_git_repo_reports_warning(tmp_path: Path) -> None:
    resolver = _StubPathResolver(tmp_path)
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    (working_dir / "x.py").write_text("x = 1\n", encoding="utf-8")

    tool = _make_tool(resolver)
    result = await tool.invoke(
        ArtifactPackInput(
            working_dir=str(working_dir),
            run_id="r1",
            include_git=True,
            include_event_log=False,
            create_zip=False,
        ),
        _context(),
    )

    assert result.success
    assert any("git evidence skipped" in warning for warning in result.output.warnings)
