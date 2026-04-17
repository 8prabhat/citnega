"""Golden orchestration scenarios across multiple built-in tools."""

from __future__ import annotations

from pathlib import Path
import shlex
import sys
from unittest.mock import MagicMock

import pytest

from citnega.packages.agents.core.orchestrator_agent import (
    OrchestrationStep,
    OrchestratorInput,
)
from citnega.packages.agents.registry import AgentRegistry
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.tools.registry import ToolRegistry


def _build_orchestrator():
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()

    tools = ToolRegistry(enforcer=enforcer, emitter=emitter, tracer=tracer).build_all()
    agents = AgentRegistry(enforcer=enforcer, emitter=emitter, tracer=tracer, tools=tools).build_all()
    return agents["orchestrator_agent"]


def _context() -> CallContext:
    return CallContext(
        session_id="golden-s1",
        run_id="golden-r1",
        turn_id="golden-t1",
        session_config=SessionConfig(
            session_id="golden-s1",
            name="golden",
            framework="direct",
            default_model_id="x",
        ),
    )


@pytest.mark.asyncio
async def test_golden_multitool_success(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "pkg").mkdir()
    (repo / "pkg" / "core.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "tests" / "unit").mkdir(parents=True)
    (repo / "tests" / "unit" / "test_core.py").write_text(
        "from pkg.core import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    orchestrator = _build_orchestrator()
    py = shlex.quote(sys.executable)

    result = await orchestrator.invoke(
        OrchestratorInput(
            goal="Run repo quality orchestration",
            working_dir=str(repo),
            steps=[
                OrchestrationStep(
                    step_id="map",
                    callable_name="repo_map",
                    task="map repository architecture",
                    args={"root_path": str(repo)},
                ),
                OrchestrationStep(
                    step_id="matrix",
                    callable_name="test_matrix",
                    task="discover tests",
                    depends_on=["map"],
                    args={"root_path": str(repo), "execute": False},
                ),
                OrchestrationStep(
                    step_id="gate",
                    callable_name="quality_gate",
                    task="run gate",
                    depends_on=["matrix"],
                    args={
                        "working_dir": str(repo),
                        "commands": [f"{py} -c \"print('gate ok')\""],
                    },
                ),
            ],
            max_retries=0,
            rollback_on_failure=True,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 0
    assert out.completed_steps == 3
    assert [s.status for s in out.step_results] == ["completed", "completed", "completed"]


@pytest.mark.asyncio
async def test_golden_failure_triggers_rollback(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "module").mkdir()
    (repo / "module" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

    orchestrator = _build_orchestrator()
    py = shlex.quote(sys.executable)

    result = await orchestrator.invoke(
        OrchestratorInput(
            goal="Run and rollback on failure",
            working_dir=str(repo),
            steps=[
                OrchestrationStep(
                    step_id="map",
                    callable_name="repo_map",
                    task="map repository",
                    args={"root_path": str(repo)},
                    rollback_callable="quality_gate",
                    rollback_args={
                        "working_dir": str(repo),
                        "commands": [f"{py} -c \"print('rollback ok')\""],
                    },
                ),
                OrchestrationStep(
                    step_id="gate",
                    callable_name="quality_gate",
                    task="fail gate intentionally",
                    depends_on=["map"],
                    args={
                        "working_dir": str(repo),
                        "commands": [f"{py} -c \"import sys; sys.exit(7)\""],
                    },
                ),
            ],
            rollback_on_failure=True,
            max_retries=0,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 1
    assert any("rollback via 'quality_gate' succeeded" in a for a in out.rollback_actions)
    map_step = next(s for s in out.step_results if s.step_id == "map")
    assert map_step.status == "rolled_back"
