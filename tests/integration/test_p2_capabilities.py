"""Integration tests for P2 horizontal capabilities (artifact_pack/security/release)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citnega.packages.agents.registry import AgentRegistry
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.storage.path_resolver import PathResolver
from citnega.packages.tools.registry import ToolRegistry


def _context() -> CallContext:
    return CallContext(
        session_id="p2-s1",
        run_id="p2-r1",
        turn_id="p2-t1",
        session_config=SessionConfig(
            session_id="p2-s1",
            name="p2",
            framework="direct",
            default_model_id="x",
        ),
    )


def _build(tmp_path: Path):
    app_home = tmp_path / "app_home"
    path_resolver = PathResolver(app_home=app_home)
    path_resolver.create_all()

    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()

    tools = ToolRegistry(
        enforcer=enforcer,
        emitter=emitter,
        tracer=tracer,
        path_resolver=path_resolver,
    ).build_all()
    agents = AgentRegistry(
        enforcer=enforcer,
        emitter=emitter,
        tracer=tracer,
        tools=tools,
    ).build_all()
    return tools, agents, path_resolver


def test_p2_callables_registered(tmp_path: Path) -> None:
    tools, agents, _ = _build(tmp_path)

    assert "artifact_pack" in tools
    assert "security_agent" in agents
    assert "release_agent" in agents


@pytest.mark.asyncio
async def test_p2_security_and_release_workflow(tmp_path: Path) -> None:
    tools, agents, path_resolver = _build(tmp_path)
    _ = tools

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "risky.py").write_text(
        'API_KEY = "abcdef1234567890"\nsubprocess.run("ls", shell=True)\n',
        encoding="utf-8",
    )

    security_agent = agents["security_agent"]
    release_agent = agents["release_agent"]

    from citnega.packages.agents.specialists.release_agent import ReleaseAgentInput
    from citnega.packages.agents.specialists.security_agent import SecurityAgentInput

    sec_result = await security_agent.invoke(
        SecurityAgentInput(
            working_dir=str(repo),
            include_repo_map=False,
            include_quality_gate=False,
            include_event_log_scan=False,
        ),
        _context(),
    )

    assert sec_result.success
    assert "Findings:" in sec_result.output.response

    rel_result = await release_agent.invoke(
        ReleaseAgentInput(
            working_dir=str(repo),
            include_quality_gate=False,
            include_test_matrix=False,
            include_repo_map=False,
            include_artifact_pack=True,
            base_ref="",
            head_ref="",
        ),
        _context(),
    )

    assert rel_result.success
    assert "Rollback plan:" in rel_result.output.response
    assert "artifact_pack" in rel_result.output.tool_calls_made
    assert any(path_resolver.artifacts_dir.rglob("*.zip"))
