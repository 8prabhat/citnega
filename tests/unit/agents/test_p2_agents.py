"""Unit tests for P2 specialist additions (security_agent, release_agent)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.tools.builtin.artifact_pack import ArtifactPackTool


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


def _deps() -> tuple[PolicyEnforcer, EventEmitter, MagicMock]:
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return enforcer, emitter, tracer


@pytest.mark.asyncio
async def test_security_agent_detects_risky_patterns(tmp_path: Path) -> None:
    from citnega.packages.agents.specialists.security_agent import SecurityAgent, SecurityAgentInput

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "risky.py").write_text(
        'API_KEY = "abcdef1234567890"\nsubprocess.run("ls", shell=True)\n',
        encoding="utf-8",
    )

    enforcer, emitter, tracer = _deps()
    agent = SecurityAgent(
        policy_enforcer=enforcer,
        event_emitter=emitter,
        tracer=tracer,
    )

    result = await agent.invoke(
        SecurityAgentInput(
            working_dir=str(tmp_path),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
        ),
        _context(),
    )

    assert result.success
    assert "Findings:" in result.output.response
    assert "inline_secret_assignment" in result.output.response
    assert "subprocess_shell_true" in result.output.response


@pytest.mark.asyncio
async def test_security_agent_uses_cache_on_second_static_scan(tmp_path: Path) -> None:
    from citnega.packages.agents.specialists.security_agent import SecurityAgent, SecurityAgentInput

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "risky.py").write_text(
        'API_KEY = "abcdef1234567890"\nsubprocess.run("ls", shell=True)\n',
        encoding="utf-8",
    )

    enforcer, emitter, tracer = _deps()
    agent = SecurityAgent(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)

    first = await agent.invoke(
        SecurityAgentInput(
            working_dir=str(tmp_path),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
            use_cache=True,
            cache_ttl_seconds=120,
        ),
        _context(),
    )
    second = await agent.invoke(
        SecurityAgentInput(
            working_dir=str(tmp_path),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
            use_cache=True,
            cache_ttl_seconds=120,
        ),
        _context(),
    )

    assert first.success and second.success
    assert "security_cache" not in first.output.sources
    assert "security_cache" in second.output.sources
    assert "inline_secret_assignment" in second.output.response


@pytest.mark.asyncio
async def test_security_agent_cache_invalidates_when_target_changes(tmp_path: Path) -> None:
    from citnega.packages.agents.specialists.security_agent import SecurityAgent, SecurityAgentInput

    (tmp_path / "app").mkdir()
    risky = tmp_path / "app" / "risky.py"
    risky.write_text('API_KEY = "abcdef1234567890"\n', encoding="utf-8")

    enforcer, emitter, tracer = _deps()
    agent = SecurityAgent(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)

    _ = await agent.invoke(
        SecurityAgentInput(
            working_dir=str(tmp_path),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
            use_cache=True,
            cache_ttl_seconds=120,
        ),
        _context(),
    )

    risky.write_text("value = 1\n", encoding="utf-8")

    second = await agent.invoke(
        SecurityAgentInput(
            working_dir=str(tmp_path),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
            use_cache=True,
            cache_ttl_seconds=120,
        ),
        _context(),
    )

    assert second.success
    assert "security_cache" not in second.output.sources
    assert "inline_secret_assignment" not in second.output.response


@pytest.mark.asyncio
async def test_release_agent_generates_handoff_with_artifact_pack(tmp_path: Path) -> None:
    from citnega.packages.agents.specialists.release_agent import ReleaseAgent, ReleaseAgentInput

    (tmp_path / "module").mkdir()
    (tmp_path / "module" / "core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    resolver = _StubPathResolver(tmp_path)
    enforcer, emitter, tracer = _deps()

    artifact_tool = ArtifactPackTool(
        policy_enforcer=enforcer,
        event_emitter=emitter,
        tracer=tracer,
        path_resolver=resolver,
    )

    agent = ReleaseAgent(
        policy_enforcer=enforcer,
        event_emitter=emitter,
        tracer=tracer,
        tool_registry={"artifact_pack": artifact_tool},
    )

    result = await agent.invoke(
        ReleaseAgentInput(
            working_dir=str(tmp_path),
            include_quality_gate=False,
            include_test_matrix=False,
            include_repo_map=False,
            include_artifact_pack=True,
            base_ref="",
            head_ref="",
        ),
        _context(),
    )

    assert result.success
    assert "Verdict:" in result.output.response
    assert "Rollback plan:" in result.output.response
    assert "artifact_pack" in result.output.tool_calls_made
    assert any(resolver.artifacts_dir.rglob("*.zip"))
