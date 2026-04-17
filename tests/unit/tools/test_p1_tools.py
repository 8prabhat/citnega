"""Unit tests for P1 built-in tools (repo_map, quality_gate)."""

from __future__ import annotations

from pathlib import Path
import shlex
import sys
from unittest.mock import MagicMock

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.tools.builtin.quality_gate import QualityGateInput, QualityGateTool
from citnega.packages.tools.builtin.repo_map import RepoMapInput, RepoMapTool
from citnega.packages.tools.builtin.test_matrix import MatrixInput, MatrixTool


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


def _make_tool(cls):
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


@pytest.mark.asyncio
async def test_repo_map_scans_repository_structure(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "lib").mkdir()
    (tmp_path / "app" / "main.py").write_text("import lib.utils\n", encoding="utf-8")
    (tmp_path / "lib" / "utils.py").write_text("from app.main import x\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("text", encoding="utf-8")

    tool = _make_tool(RepoMapTool)
    result = await tool.invoke(
        RepoMapInput(root_path=str(tmp_path), include_tests=True),
        _context(),
    )

    assert result.success
    assert result.output.python_files_scanned == 2
    assert any(s.startswith("app:") for s in result.output.top_modules)
    assert result.output.summary


@pytest.mark.asyncio
async def test_quality_gate_custom_commands_reports_failures() -> None:
    tool = _make_tool(QualityGateTool)
    py = shlex.quote(sys.executable)
    result = await tool.invoke(
        QualityGateInput(
            commands=[
                f"{py} -c \"print('ok')\"",
                f"{py} -c \"import sys; sys.exit(3)\"",
            ],
            per_command_timeout_seconds=20,
        ),
        _context(),
    )

    assert result.success
    assert result.output.total_checks == 2
    assert result.output.failed_checks == 1
    assert result.output.passed is False


@pytest.mark.asyncio
async def test_quality_gate_timeout_is_reported() -> None:
    tool = _make_tool(QualityGateTool)
    py = shlex.quote(sys.executable)
    result = await tool.invoke(
        QualityGateInput(
            commands=[f"{py} -c \"import time; time.sleep(2)\""],
            per_command_timeout_seconds=0.2,
        ),
        _context(),
    )

    assert result.success
    assert result.output.total_checks == 1
    assert result.output.checks[0].return_code == 124
    assert result.output.passed is False


@pytest.mark.asyncio
async def test_test_matrix_discovers_bucketed_tests(tmp_path: Path) -> None:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "integration").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_alpha.py").write_text("def test_a():\n    assert True\n")
    (tmp_path / "tests" / "integration" / "test_beta.py").write_text(
        "def test_b():\n    assert True\n"
    )

    tool = _make_tool(MatrixTool)
    result = await tool.invoke(
        MatrixInput(root_path=str(tmp_path), execute=False),
        _context(),
    )

    assert result.success
    assert result.output.discovered_tests == 2
    assert result.output.buckets.get("unit") == 1
    assert result.output.buckets.get("integration") == 1
    assert result.output.executed is False


@pytest.mark.asyncio
async def test_repo_map_uses_cache_on_second_run(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")

    tool = _make_tool(RepoMapTool)
    first = await tool.invoke(
        RepoMapInput(root_path=str(tmp_path), use_cache=True, cache_ttl_seconds=3600),
        _context(),
    )
    second = await tool.invoke(
        RepoMapInput(root_path=str(tmp_path), use_cache=True, cache_ttl_seconds=3600),
        _context(),
    )

    assert first.success and second.success
    assert first.output.cache_hit is False
    assert second.output.cache_hit is True


@pytest.mark.asyncio
async def test_test_matrix_uses_cache_for_discovery(tmp_path: Path) -> None:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_alpha.py").write_text("def test_a():\n    assert True\n")

    tool = _make_tool(MatrixTool)
    first = await tool.invoke(
        MatrixInput(root_path=str(tmp_path), execute=False, use_cache=True, cache_ttl_seconds=3600),
        _context(),
    )
    second = await tool.invoke(
        MatrixInput(root_path=str(tmp_path), execute=False, use_cache=True, cache_ttl_seconds=3600),
        _context(),
    )

    assert first.success and second.success
    assert first.output.cache_hit is False
    assert second.output.cache_hit is True
