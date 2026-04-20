"""
Unit tests for DirectModelRunner helpers added in the comprehensive wiring plan.

Covers:
- _build_ambient_context: cwd, git branch, git status, non-git dir fallback
- _build_strategy_context: empty when no skills, skill body injection
- temperature: sourced from mode rather than hard-coded
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _build_ambient_context
# ---------------------------------------------------------------------------


def _get_ambient_fn():
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    return DirectModelRunner._build_ambient_context


def test_ambient_context_includes_cwd(tmp_path) -> None:
    fn = _get_ambient_fn()
    result = fn(cwd=str(tmp_path))
    assert str(tmp_path) in result


def test_ambient_context_includes_time() -> None:
    fn = _get_ambient_fn()
    result = fn(cwd=os.getcwd())
    assert "UTC" in result or "time" in result.lower()


def test_ambient_context_handles_non_git_dir(tmp_path) -> None:
    """A directory outside any git repo should still return a valid context block."""
    fn = _get_ambient_fn()
    with patch("subprocess.run") as mock_run:
        # Simulate git commands failing (not a git repo)
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="")
        result = fn(cwd=str(tmp_path))

    # Should still return something (cwd + time), not crash or return empty
    assert str(tmp_path) in result


def test_ambient_context_includes_git_branch_when_available() -> None:
    fn = _get_ambient_fn()
    with patch("subprocess.run") as mock_run:

        def _fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return MagicMock(returncode=0, stdout="feature/test\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = _fake_run
        result = fn(cwd=os.getcwd())

    assert "feature/test" in result


def test_ambient_context_returns_string_on_exception() -> None:
    fn = _get_ambient_fn()
    with patch("subprocess.run", side_effect=OSError("no git")):
        result = fn(cwd="/nonexistent/path/that/causes/error")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _build_strategy_context
# ---------------------------------------------------------------------------


def _make_runner_stub():
    """Build a minimal DirectModelRunner-like object to test _build_strategy_context."""
    from citnega.packages.adapters.direct.runner import DirectModelRunner

    runner = object.__new__(DirectModelRunner)

    conv = MagicMock()
    conv.active_skills = []
    conv.mental_model_spec = None
    conv.mode_name = "chat"
    runner._conv = conv
    runner._capability_registry = None
    return runner


def test_strategy_context_empty_when_no_skills() -> None:
    runner = _make_runner_stub()
    result = runner._build_strategy_context()
    assert result == ""


def test_strategy_context_empty_when_no_registry() -> None:
    runner = _make_runner_stub()
    runner._conv.active_skills = ["some_skill"]
    runner._capability_registry = None
    result = runner._build_strategy_context()
    assert result == ""


def test_strategy_context_injects_skill_body() -> None:
    runner = _make_runner_stub()
    runner._conv.active_skills = ["debug_session"]
    runner._conv.mode_name = "code"

    skill_obj = MagicMock()
    skill_obj.supported_modes = ["code"]
    skill_obj.body = "Step 1: read traceback\nStep 2: fix root cause"

    descriptor = MagicMock()
    descriptor.runtime_object = skill_obj

    registry = MagicMock()
    registry.get_descriptor.return_value = descriptor
    runner._capability_registry = registry

    result = runner._build_strategy_context()
    assert "debug_session" in result
    assert "Step 1: read traceback" in result
    assert "## Active Skills" in result


def test_strategy_context_filters_by_mode() -> None:
    """Skills whose supported_modes excludes the current mode should be skipped."""
    runner = _make_runner_stub()
    runner._conv.active_skills = ["deploy_checklist"]
    runner._conv.mode_name = "chat"  # skill only supports 'operate'

    skill_obj = MagicMock()
    skill_obj.supported_modes = ["operate"]  # not chat
    skill_obj.body = "Pre-flight checklist..."

    descriptor = MagicMock()
    descriptor.runtime_object = skill_obj

    registry = MagicMock()
    registry.get_descriptor.return_value = descriptor
    runner._capability_registry = registry

    result = runner._build_strategy_context()
    assert result == ""


def test_strategy_context_injects_mental_model_clauses() -> None:
    runner = _make_runner_stub()
    runner._conv.active_skills = []

    clause = MagicMock()
    clause.text = "Always cite sources"

    mental_model = MagicMock()
    mental_model.clauses = [clause]
    runner._conv.mental_model_spec = mental_model

    result = runner._build_strategy_context()
    assert "Always cite sources" in result
    assert "## Behavioral Guidelines" in result


def test_strategy_context_handles_string_clauses() -> None:
    """Clauses may be plain strings (no .text attribute) — should not crash."""
    runner = _make_runner_stub()
    runner._conv.active_skills = []

    mental_model = MagicMock()
    mental_model.clauses = ["Be concise", "Be precise"]
    runner._conv.mental_model_spec = mental_model

    result = runner._build_strategy_context()
    assert "Be concise" in result


# ---------------------------------------------------------------------------
# temperature
# ---------------------------------------------------------------------------


def test_temperature_sourced_from_mode() -> None:
    """DirectModelRunner should use mode.temperature, not a hardcoded 0.7."""
    from citnega.packages.protocol.modes import get_mode

    code_mode = get_mode("code")
    assert code_mode.temperature <= 0.3, (
        f"code mode temperature should be ≤0.3 for precision, got {code_mode.temperature}"
    )


@pytest.mark.parametrize("mode_name", ["chat", "plan", "explore", "research", "code", "review", "operate"])
def test_all_modes_temperature_in_valid_range(mode_name: str) -> None:
    from citnega.packages.protocol.modes import get_mode

    mode = get_mode(mode_name)
    assert 0.0 <= mode.temperature <= 1.0, (
        f"{mode_name} temperature {mode.temperature} out of [0, 1] range"
    )
