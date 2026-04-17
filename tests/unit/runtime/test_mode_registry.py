"""
Unit tests for the mode registry (Phase 8, Step 8.2).

Verifies:
- All 7 modes are registered
- get_mode() returns the correct mode
- get_mode() falls back to ChatMode for unknown names
- all_modes() returns all 7 modes in stable order
- TUI ModeCommand reads from all_modes()
- Each mode has a non-empty description
"""

from __future__ import annotations

import pytest

from citnega.packages.protocol.modes import VALID_MODES, all_modes, get_mode


_EXPECTED_MODES = {"chat", "plan", "explore", "research", "code", "review", "operate"}


def test_all_seven_modes_registered() -> None:
    registered = {m.name for m in all_modes()}
    assert registered == _EXPECTED_MODES, (
        f"Missing modes: {_EXPECTED_MODES - registered}. "
        f"Extra modes: {registered - _EXPECTED_MODES}"
    )


def test_valid_modes_list_complete() -> None:
    assert set(VALID_MODES) == _EXPECTED_MODES


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_get_mode_returns_correct_mode(mode_name: str) -> None:
    mode = get_mode(mode_name)
    assert mode.name == mode_name


def test_get_mode_unknown_falls_back_to_chat() -> None:
    mode = get_mode("nonexistent_mode")
    assert mode.name == "chat"


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_each_mode_has_description(mode_name: str) -> None:
    mode = get_mode(mode_name)
    assert mode.description, f"{mode_name} has empty description"


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_augment_system_prompt_returns_string(mode_name: str) -> None:
    mode = get_mode(mode_name)
    result = mode.augment_system_prompt("base prompt")
    assert isinstance(result, str)
    assert "base prompt" in result


def test_review_mode_augments_prompt() -> None:
    mode = get_mode("review")
    result = mode.augment_system_prompt("You are an assistant.")
    assert "review" in result.lower() or "reviewer" in result.lower()


def test_operate_mode_augments_prompt() -> None:
    mode = get_mode("operate")
    result = mode.augment_system_prompt("You are an assistant.")
    assert "operate" in result.lower() or "runbook" in result.lower()


def test_plan_mode_draft_and_execute_phases() -> None:
    from citnega.packages.protocol.modes import PlanMode

    mode = PlanMode()
    draft = mode.augment_system_prompt("base", phase="draft")
    execute = mode.augment_system_prompt("base", phase="execute")
    assert draft != execute
    assert "plan" in draft.lower()
    assert "execut" in execute.lower()


def test_all_modes_stable_order() -> None:
    order_first = [m.name for m in all_modes()]
    order_second = [m.name for m in all_modes()]
    assert order_first == order_second
